from django import forms
from ai_imposter.ai_client import MODELS

class GameForm(forms.Form):
    ai_model = forms.ChoiceField(
        choices=[(model, model) for model in MODELS]
    )
