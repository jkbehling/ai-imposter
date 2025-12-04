from django import forms
from ai_imposter.ai_client import get_models

class GameForm(forms.Form):
    ai_model = forms.ChoiceField(
        choices=[(model, model) for model in get_models()]
    )
