import logging
import asyncio

from django.conf import settings
from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)



class AIClientError(Exception):
    """
    A custom error wrapper for any errors raised while using the
    OpenAIClient class methods.
    """
    pass

INSTRUCTIONS = (
    'You are participating in a game where players answer questions and vote on who they think '
    'the AI imposter is. You will be provided with the question, followed by the players\' answers. '
    'Answer the question by blending in with the other answers so you aren\'t found out as the imposter. '
    'You are not allowed to copy other player\'s answer\'s exactly, but you can draw inspiration from them . '
    'Respond in a casual way with basic high-school level vocabulary and grammar. '
    'Don\'t use perfect grammar or punctuation, and avoid using the em dash character. '
    'Occasionally use minor typos. '
    'Keep your response about the same length as the other answers. '
    'Don\'t respond with anything other than your answer to the question.'
)

class MockClient:
    def __init__(self, model):
        self.model = model

    async def get_ai_answer(self, question, answers):
        # Simulate an AI response by blending in with the other answers
        # Use asyncio.sleep so this doesn't block the event loop
        await asyncio.sleep(5)
        return "This is a mock response."

class OpenAIClient:
    def __init__(self, model):
        self.client = OpenAI()
        self.model = model

    async def get_ai_answer(self, question, answers):
        try:
            answers = "\n".join(answers)
            response = await asyncio.to_thread(
                self.client.responses.create,
                model=self.model,
                input=[
                    {'role': 'system', 'content': INSTRUCTIONS},
                    {'role': 'user', 'content': f'Question: {question}\nAnswers: {answers}'},
                ],
            )            
        except OpenAIError as e:
            error_msg = f'OpenAI API error: {e}'
            logger.error(error_msg)
            raise AIClientError(error_msg)

        return response.output_text

def get_models():
    """Return available models, including dev model if in DEBUG mode."""
    models = {
        'gpt-4.1': OpenAIClient,
        'gpt-5-nano': OpenAIClient,
        'gpt-5.1': OpenAIClient,
    }
    if settings.DEBUG:
        models['dev'] = MockClient
    return models

async def get_ai_answer(model, question, answers):
    models = get_models()
    if not model in models:
        raise ValueError(f"Unknown model: {model}")

    client = models[model](model)
    return await client.get_ai_answer(question, answers)