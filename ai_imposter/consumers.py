import json
import asyncio
import datetime
import traceback
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string
from ai_imposter.game_state import GameState, games


class GameConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_id: str = None
        self.game: GameState = None
        self.game_group_name: str = None
        self.event_handlers: dict = {
            "change_name": self.handle_change_name,
            "start_game": self.handle_start_game,
            "skip_stage": self.handle_skip_stage,
            "ask_question": self.handle_ask_question,
            "answer_question": self.handle_answer_question,
            "vote": self.handle_vote,
            "play_again": self.handle_play_again,
        }

    async def connect(self):
        self.game_id = self.scope["url_route"]["kwargs"]["game_id"]
        self.game_group_name = f"game_{self.game_id}"
        self.game = games.get(self.game_id)
        if not self.game:
            await self.close(code=4000)
            return
        await self.channel_layer.group_add(
            self.game_group_name, self.channel_name
        )
        await self.accept()
        was_new_player = self.game.add_player(self.scope["session"].session_key, self.channel_name)
        context = {
            "player": self.game.get_player(self.scope["session"].session_key)
        }
        if was_new_player:
            context["add"] = True
        else:
            context["update"] = True
        await self.group_send_html(
            "game.html#player-partial",
            context
        )

    async def disconnect(self, close_code):
        session_key = self.scope["session"].session_key
        deleted_player = self.game.get_player(session_key)
        self.game.remove_player(session_key)
        await self.channel_layer.group_discard(
            self.game_group_name, self.channel_name
        )
        await self.group_send_html(
            "game.html#player-partial",
            {
                "player": deleted_player,
                "update": True,
            }
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        event = data.get("event")
        event_handler = self.event_handlers.get(event)
        if event_handler:
            try:
                template, context = await event_handler(data)
                # If an empty template is returned, a skip has happened that initiated the next stage
                if not template:
                    return
                # Send the returned partial to players first.
                await self.group_send_html(template, context)
            except Exception as e:
                traceback.print_exc()
                await self.send(
                    text_data=render_to_string("game.html#error-partial", {"error_message": "Something went wrong..."})
                )
        else:
            error_html = render_to_string("game.html#error-partial", {"error_message": "Unknown event"})
            await self.send(text_data=error_html)

    async def group_send_html(self, template, context={}, players=[]):
        if not players:
            players = self.game.connected_players()
        for player in players:
            html = render_to_string(
                template,
                {**context, "game": self.game, "current_player": player}
            )            
            await self.channel_layer.send(
                player.channel_name,
                {"type": "send.html", "html": html}
            )

    async def send_html(self, event):
        await self.send(text_data=event["html"])

    async def create_start_stage_task(self, stage):
        def _on_start_stage_created(future):
            # Handle the completion of the start_stage task
            if future.cancelled():
                pass
                # print("Start stage task was cancelled")
            elif future.exception():
                print(f"Start stage task raised an exception: {future.exception()}")
            else:
                pass
                # print("Start stage task completed successfully")
        # Create the task to start the stage
        task = asyncio.create_task(self.start_stage(stage))
        task.add_done_callback(_on_start_stage_created)

    async def start_stage(self, stage):
        # Cancel any previously queued transition (one per game) before starting a new stage
        if getattr(self.game, "queued_stage", None):
            await self.cancel_queued_stage()

        self.game.stage = stage
        self.game.stage.timer_start = datetime.datetime.now()
        self.game.stage.timer_end = (
            datetime.datetime.now() + datetime.timedelta(seconds=self.game.stage.duration)
        )
        # Call the stage's before_start hook. It may be async; if so, await it.
        try:
            result = self.game.stage.before_start()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            # Ensure the consumer doesn't crash if before_start fails
            traceback.print_exc()
        await self.group_send_html("game.html#game-partial")
        # Schedule the next stage to start after the CURRENT stage's duration
        next_stage = self.game.next_stage
        if next_stage and next_stage.duration:
            # pass the current stage duration as the delay so we wait the right amount
            self.game.queued_stage = asyncio.create_task(self.queue_stage(next_stage, delay=self.game.stage.duration))

    async def queue_stage(self, stage, delay: int):
        """Wait `delay` seconds then start `stage`.

        If the sleep is cancelled, return without starting the stage.
        """
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            # The queued transition was cancelled; do not start the stage
            return

        if stage:
            await self.start_stage(stage)

    async def cancel_queued_stage(self):
        """Cancel and await the currently queued transition task (if any).

        This ensures the cancellation completes before proceeding.
        """
        task = getattr(self.game, "queued_stage", None)
        if not task:
            return
        if task.done():
            self.game.queued_stage = None
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            # expected when cancelling
            pass
        finally:
            self.game.queued_stage = None

    async def handle_change_name(self, data):
        new_name = data.get("name")
        if not new_name:
            raise Exception("Name is required")
        player = self.game.get_player(self.scope["session"].session_key)
        player.name = new_name
        return "game.html#player-partial", {"player": player, "update": True}

    async def handle_start_game(self, data):
        self.game.select_next_questioner()
        await self.create_start_stage_task(self.game.next_stage)
        return "", {}

    async def handle_skip_stage(self, data):
        if not self.game.stage.skipable:
            raise Exception("This stage cannot be skipped")
        await self.create_start_stage_task(self.game.next_stage)
        return '', {}

    async def handle_ask_question(self, data):
        question = data.get("question")
        if not self.game.stage == self.game.stages.QUESTION:
            raise Exception("You are not allowed to ask a question at this stage")
        if not question:
            raise Exception("Question required")
        if self.game.questioner and not self.game.questioner.id == self.scope["session"].session_key:
            raise Exception("You are not the questioner")

        self.game.question = question
        await self.create_start_stage_task(self.game.next_stage)
        return "", {}

    async def handle_answer_question(self, data):
        answer = data.get("answer")
        if not self.game.stage == self.game.stages.ANSWER:
            raise Exception("You are not allowed to answer at this stage")
        if not answer:
            raise Exception("Answer required")
        if answer == 'error':
            raise Exception("Test Error")
        if self.game.get_player(self.scope["session"].session_key) not in self.game.answering_players():
            raise Exception("You are not allowed to answer this question")

        player = self.game.get_player(self.scope["session"].session_key)
        player.answer = answer
        if self.game.did_all_players_answer():
            await self.create_start_stage_task(self.game.next_stage)
            return "game.html#waiting-on-ai-partial", {"waiting_on_ai_answer": True}
        await self.group_send_html("game.html#answer-form-partial", {}, [player])
        return "game.html#waiting-on-players-partial", {}

    async def handle_vote(self, data):
        player_id = data.get("player")
        if not self.game.stage == self.game.stages.SHOW_ANSWERS:
            raise Exception("Voting is not allowed at this stage")
        if not player_id:
            raise Exception("Player ID required")
        if self.game.get_player(self.scope["session"].session_key) not in self.game.voting_players():
            raise Exception("You are not allowed to vote")
        self.game.cast_vote(self.scope["session"].session_key, player_id)
        if self.game.did_all_players_vote():
            await self.create_start_stage_task(self.game.next_stage)
            return "", {}
        return "game.html#waiting-on-votes-partial", {}

    async def handle_play_again(self, data):
        if not self.game.stage == self.game.stages.ENDING:
            raise Exception("You can only play again at the end of the game")
        self.game.reset()
        return "game.html#game-partial", {}