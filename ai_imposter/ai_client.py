import logging
import asyncio

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
    'You are not allowed to copy other player\'s answer\'s exactly, but you can draw inspiration from them .'
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

MODELS = {
    'dev': MockClient,
    'gpt-5-nano': OpenAIClient
}

async def get_ai_answer(model, question, answers):
    if not model in MODELS:
        raise ValueError(f"Unknown model: {model}")

    client = MODELS[model](model)
    return await client.get_ai_answer(question, answers)