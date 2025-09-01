import random
import asyncio
import json
import uuid

from ai_imposter.ai_client import get_ai_answer

class Stage:
    def __init__(self, name, duration=0, before_start=(lambda: None), skipable=False):
        self.name = name
        self.duration = duration
        self.before_start = before_start
        self.timer_start = None
        self.timer_end = None
        self.skipable = skipable

    def __str__(self):
        return self.name

class Stages:
    LOBBY = Stage("lobby")
    INTRO = Stage("intro", duration=5, skipable=True)
    QUESTION = Stage("question", duration=30)
    ANSWER = Stage("answer", duration=30)
    SHOW_ANSWERS = Stage("show_answers", duration=30)
    ELIMINATE = Stage("eliminate", duration=15, skipable=True)
    ENDING = Stage("ending")

class GameState:
    TEAM_HUMAN = 'TEAM_HUMAN'
    TEAM_AI = 'TEAM_AI'

    def __init__(self, id, ai_model):
        self.id = id
        self.ai_model = ai_model
        # Generate a uuid for the ai player
        self.ai_player_id = str(uuid.uuid4())
        self.players: dict[str, Player] = {
            self.ai_player_id: Player(self.ai_player_id, 'AI Player', is_ai=True)
        }
        self.stages = Stages
        # Assign before_start hooks to the stages
        self.stages.ANSWER.before_start = self.before_answer
        self.stages.SHOW_ANSWERS.before_start = self.before_show_answers
        self.stages.ELIMINATE.before_start = self.eliminate_player
        self.stage = Stages.LOBBY
        # Task for the next staged transition (one per game)
        self.queued_stage: asyncio.Task | None = None
        self.questioner = None
        self.question = None
        self.eliminated_player = None
        self.winner = None # TEAM_HUMAN or TEAM_AI

    @property
    def next_stage(self):
        if self.stage == Stages.LOBBY:
            return Stages.INTRO
        elif self.stage == Stages.INTRO:
            return Stages.QUESTION
        elif self.stage == Stages.QUESTION:
            return Stages.ANSWER
        elif self.stage == Stages.ANSWER:
            return Stages.SHOW_ANSWERS
        elif self.stage == Stages.SHOW_ANSWERS:
            return Stages.ELIMINATE
        elif self.stage == Stages.ELIMINATE:
            if not self.winner:
                return Stages.QUESTION
            return Stages.ENDING
        elif self.stage == Stages.ENDING:
            return Stages.LOBBY
        return None

    def add_player(self, player_id, channel_name):
        if player_id not in self.players:
            self.players[player_id] = Player(
                player_id,
                f"Player {len(self.players)}", 
                channel_name
            )
        else:
            self.players[player_id].channel_name = channel_name
            self.players[player_id].connected = True

    def remove_player(self, player_id):
        if player_id in self.players:
            self.players[player_id].connected = False

    def connected_players(self):
        return [p for p in self.players.values() if p.connected and not p.is_ai]

    def answering_human_players(self):
        return [p for p in self.connected_players() if p.id != self.questioner.id and not p.eliminated]

    def answering_players(self):
        all_players = self.answering_human_players() + [self.get_player(self.ai_player_id)]
        random.shuffle(all_players)
        return all_players

    def remaining_players(self):
        return [p for p in self.connected_players() if not p.eliminated]

    def eligible_questioner_players(self):
        return [p for p in self.connected_players() if not p.asked_question and not p.eliminated]

    def voting_players(self):
        return [p for p in self.connected_players() if not p.eliminated]

    def get_player(self, player_id):
        return self.players.get(player_id)

    def get_waiting_on_num_players_to_answer(self):
        return sum(1 for p in self.answering_human_players() if not p.answer)

    def did_all_players_answer(self):
        return all(p.answer for p in self.answering_human_players())

    def get_human_answers(self):
        return [p.answer for p in self.answering_human_players()]

    def start_game(self):
        self.stage = Stages.INTRO

    def select_next_questioner(self):
        connected_players = self.connected_players()
        options = self.eligible_questioner_players()
        if options:
            self.questioner = random.choice(options)
        else:
            for player in connected_players:
                player.asked_question = False
            self.questioner = random.choice(self.eligible_questioner_players())
        self.questioner.asked_question = True

    def cast_vote(self, voter_id, target_id):
        voter = self.get_player(voter_id)
        target = self.get_player(target_id)
        voter.voted = True
        voter.targeted_player = target
        target.num_votes += 1

    def did_all_players_vote(self):
        return all(p.voted for p in self.voting_players())

    def get_waiting_on_num_players_to_vote(self):
        return sum(1 for p in self.connected_players() if not p.voted)

    def eliminate_player(self):
        players = list(self.answering_players())
        if not players:
            return
        # Find the highest vote count among answering players
        max_votes = max((p.num_votes for p in players), default=0)
        # If no one has any votes, or there's a tie for top votes, do not eliminate anyone
        if max_votes == 0:
            return
        top_players = [p for p in players if p.num_votes == max_votes]
        if len(top_players) != 1:
            # tie -> no elimination
            self.eliminated_player = None
            return
        player_with_most_votes = top_players[0]
        player_with_most_votes.eliminated = True
        self.eliminated_player = player_with_most_votes
        # Humans win if they eliminate the AI
        if self.eliminated_player == self.players[self.ai_player_id]:
            self.winner = self.TEAM_HUMAN
            return
        # Ai wins if it remains with the last human player
        if len(self.remaining_players()) <= 1:
            self.winner = self.TEAM_AI

    def before_answer(self):
        # Reset values
        for player in self.players.values():
            player.answer = ''
            player.voted = False
            player.targeted_player = None
            player.num_votes = 0

    async def before_show_answers(self):
        # Mock the AI player's answer
        ai_player = self.players.get(self.ai_player_id)
        ai_player.answer = await get_ai_answer(
            self.ai_model,
            self.question,
            self.get_human_answers()
        )

    def reset(self):
        self.stage = Stages.LOBBY
        self.questioner = None
        self.question = None
        self.eliminated_player = None
        self.winner = None
        for player in self.players.values():
            player.asked_question = False
            player.answer = ''
            player.voted = False
            player.targeted_player = None
            player.num_votes = 0
            player.eliminated = False

    def to_json(self):
        return json.dumps({
            "players": self.players,
            "messages": self.messages
        })

games: dict[int, GameState] = {}

class Player:

    def __init__(self, id, name, channel_name='', is_ai=False):
        self.id = id
        self.name = name
        self.is_ai = is_ai
        self.channel_name = channel_name
        self.connected = True
        self.asked_question = False
        self.answer = ''
        self.voted = False
        self.targeted_player = None
        self.num_votes = 0
        self.eliminated = False

    @property
    def can_answer_question(self):
        return self.connected and not self.asked_question and not self.eliminated and not self.answer

    @property
    def can_vote(self):
        return self.connected and not self.eliminated and not self.voted