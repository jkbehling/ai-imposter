import uuid
from django.views import View
from django.shortcuts import render, redirect
from django.http import Http404

from ai_imposter.forms import GameForm
from ai_imposter.game_state import GameState, games

class HomeView(View):

    def get(self, request):
        request.session['init'] = True
        context = {
            'form': GameForm() 
        }
        return render(request, 'home.html', context)

    def post(self, request):
        """
        Initialize a new game and redirect to the game room.
        """
        form = GameForm(request.POST)
        if not form.is_valid():
            return render(request, 'home.html', {'form': form})
        game_id = uuid.uuid4().hex[:5]
        game_state = GameState(game_id, form.cleaned_data['ai_model'])
        games[game_id] = game_state
        return redirect('game', game_id=game_id)

class GameView(View):

    def get(self, request, game_id):
        request.session['init'] = True
        game = games.get(game_id)
        if not game:
            games[game_id] = GameState(game_id, 'dev')
            return redirect('game', game_id=game_id)
        #     raise Http404("Game not found")
        context = {
            'game': game
        }
        return render(request, 'game.html', context)

