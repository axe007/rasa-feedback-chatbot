from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.interfaces import Action
from rasa_sdk.events import (
    ActionExecuted,
    SlotSet,
    EventType,
    FollowupAction,
    UserUtteranceReverted,
    UserUttered
)
from typing import Dict, Text, Any, List
import openai
import os

from openai import AzureOpenAI

# Initialize the Azure OpenAI client with the API key and endpoint from environment variables
client = AzureOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    api_version="2024-02-15-preview",
    azure_endpoint=os.environ.get("OPENAI_ENDPOINT")
)

# Set the OpenAI API key for the openai library from environment variables
openai.api_key = os.getenv("OPENAI_API_KEY")

class ActionFallbackToLLM(Action):
    """Custom action to handle fallback to a large language model (LLM)"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_fallback_to_llm"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        dispatcher.utter_message(text="Hold on while I'm asking from a friend...")

        # If chatbot could not identify intent above threshold, then user message is sent to LLM along of list of
        # possible intent to try to identify and respond accordingly
        intents_description = """
            Label a user's message from a conversation with an intent. Reply ONLY with the name of the intent.
            The intent should be one of the following:
            - explain_feature
            - find_page
            - mongolian_greeting
            - non_english
            - provide_feature_request (provide a request for a new feature or function)
            - provide_bug_report (report a software bug or software errors)
            - provide_generic_comment (provide a non-specific generic comment)
            - out_of_scope
        """

        # Prepare the messages for the LLM request
        messages = [
            {"role": "system", "content": intents_description},
            {"role": "user", "content": tracker.latest_message.get('text')}
        ]

        try:
            # Send the user's message to the LLM for intent prediction
            response = client.chat.completions.create(
                model="gpt-35-fallback",
                messages=messages,
                temperature=0.7,
                max_tokens=1500,
                top_p=0.95,
                stop=None
            )

            # Get the response text from the LLM
            response_text = response.choices[0].message.content.strip().lower()

            # List of valid intents
            valid_intents = [
                'explain_feature', 'find_page', 'mongolian_greeting', 'non_english', 'help', 'inform',
                'thankyou', 'provide_feature_request', 'provide_bug_report', 'provide_generic_comment', 'out_of_scope'
            ]

            # If the response is a valid intent, return the corresponding action
            if response_text in valid_intents:
                data = {
                    "intent": {
                        "name": response_text,
                        "confidence": 1.0,
                    }
                }
                return [ActionExecuted("action_listen"), UserUttered(text=response_text, parse_data=data)]
            else:
                # If the response is not a valid intent, notify the user
                dispatcher.utter_message(text="Sorry, I couldn't identify the intent. Try again later.")

        except Exception as e:
            # Handle exceptions and notify the user
            dispatcher.utter_message(text="Sorry, I couldn't get a response. Try again later.")
            print(f"Error with LLM call: {e}")

        # If intent could not be identified, revert the user's utterance and listen for the next input
        return [UserUtteranceReverted(), FollowupAction(name="action_listen")]
