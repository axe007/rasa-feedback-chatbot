"""Custom actions"""
import os
from typing import Dict, Text, Any, List
import logging
from dateutil import parser
import sqlalchemy as sa
import json
from openai import AzureOpenAI
from datetime import datetime

client = AzureOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    api_version="2024-02-15-preview",
    azure_endpoint=os.environ.get("OPENAI_ENDPOINT")
)

from rasa_sdk.interfaces import Action
from rasa_sdk.events import (
    ActionExecuted,
    ActiveLoop,
    EventType,
    FollowupAction,
    Form,
    Restarted,
    SessionStarted,
    SlotSet,
    UserUtteranceReverted,
)
from rasa_sdk.types import DomainDict
from rasa_sdk import Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher

import psycopg2
import psycopg2.extras

from actions.profile_db import create_database, ProfileDB
from actions.custom_forms import CustomFormValidationAction

logger = logging.getLogger(__name__)

# The profile database is created/connected to when the action server starts
# It is populated the first time `ActionSessionStart.run()` is called .
PROFILE_DB_NAME = os.environ.get("PROFILE_DB_NAME", "profile")
PROFILE_DB_URL = os.environ.get("PROFILE_DB_URL", f"sqlite:///{PROFILE_DB_NAME}.db")
ENGINE = sa.create_engine(PROFILE_DB_URL)
create_database(ENGINE, PROFILE_DB_NAME)

profile_db = ProfileDB(ENGINE)

NEXT_FORM_NAME = {
    "feature_request": "feature_request_form",
    "bug_report": "bug_report_form",
    "generic_comment": "generic_comment_form",
}

FORM_DESCRIPTION = {
    "feature_request_form": "request new feature", # Form to request new feature or function
    "bug_report_form": "report bug and errors", # Form to report a bug
    "generic_comment_form": "provide comments and feedback", # Form for generic comment or feedback
}

class ActionCheckMongolianGreeting(Action):

    def name(self) -> Text:
        return "action_check_mongolian_greeting"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Check if the Mongolian greeting was used before
        if tracker.get_slot("mongolian_greeting_used"):
            # User has greeted in Mongolian before
            dispatcher.utter_message(response="utter_non_english")
        else:
            # First time the user is greeting in Mongolian
            dispatcher.utter_message(response="utter_greet_mongolian")
            # Set the slot so we know they've used the Mongolian greeting
            return [SlotSet("mongolian_greeting_used", True)]

        return []

class ActionProvidePageInfo(Action):

    def name(self) -> Text:
        return "action_find_page"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Construct the absolute path to the JSON file
        dir_path = os.path.dirname(os.path.realpath(__file__))
        json_file_path = os.path.join(dir_path, 'pages_info.json')

        # Load pages URL info data
        with open(json_file_path) as json_file:
            pages_data = json.load(json_file)

        # Extract the slot 'page' if it exists
        page_slot = tracker.get_slot('page')
        if page_slot:
            page_slot = page_slot.lower()  # Convert to lower case for case-insensitive matching
            for page in pages_data:
                if page_slot == page["keyword"].lower():  # Check if the slot matches the keyword
                    dispatcher.utter_message(text=f"Here is the information you requested: <a target='_new' href='{page['url']}' >{page['url']}</a>")
                    return []

        dispatcher.utter_message(text="Sorry, I couldn't find the information you were looking for.")
        return []

class ActionExplainSoftwarePart(Action):

    def name(self) -> Text:
        return "action_explain_feature"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Construct the absolute path to the JSON file
        dir_path = os.path.dirname(os.path.realpath(__file__))
        json_file_path = os.path.join(dir_path, 'help_descriptions.json')

        # Load explanations of functions data
        with open(json_file_path) as json_file:
            parts_data = json.load(json_file)

        # Extract the slot 'feature' if it exists
        feature_slot = tracker.get_slot('feature_to_explain')
        if feature_slot:
            feature_slot = feature_slot.lower()  # Convert to lower case for case-insensitive matching
            for feature in parts_data:
                if feature_slot == feature["keyword"].lower():  # Check if the slot matches the keyword
                    dispatcher.utter_message(text=f"Here is the explanation: {feature['explanation']}")
                    return []

        dispatcher.utter_message(text="Sorry, I couldn't find the explanation you were looking for.")
        return []

class ActionRequestFeature(Action):
    """Request new feature."""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_request_feature"

    def get_db_connection(self):
        """Create and return a new database connection."""
        try:
            connection = psycopg2.connect(
                dbname=os.environ.get("RASA_DB_NAME"),
                user=os.environ.get("RASA_DB_USER"),
                password=os.environ.get("RASA_DB_PASSWORD"),
                host=os.environ.get("RASA_DB_HOST"),
                port=os.environ.get("RASA_DB_PORT")
            )

            return connection
        except Exception as e:
            print("Unable to connect to the database:", e)
            return None

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Executes the action"""

        # Retrieve slots
        bb_request_description = tracker.get_slot("bb_request_description")
        feature_form_temp_goal = tracker.get_slot("feature_form_temp_goal")
        feature_form_temp_challenges = tracker.get_slot("feature_form_temp_challenges")
        feature_form_temp_use_case = tracker.get_slot("feature_form_temp_use_case")
        feature_form_temp_area = tracker.get_slot("feature_form_temp_area")
        feature_form_temp_criteria = tracker.get_slot("feature_form_temp_criteria")
        feature_form_temp_priority = tracker.get_slot("feature_form_temp_priority")

        feature_challenges = tracker.get_slot("feature_challenges")
        feature_use_case = tracker.get_slot("feature_use_case")
        feature_target_area = tracker.get_slot("feature_target_area")
        feature_goal = tracker.get_slot("feature_goal")
        feature_criteria = tracker.get_slot("feature_criteria")
        feature_priority = tracker.get_slot("feature_priority")
        feature_description = tracker.get_slot("feature_description")
        user_story = tracker.get_slot("user_story")

        # Build initial_description JSON
        initial_description = json.dumps({
            "bb_request_description": bb_request_description,
            "feature_form_temp_goal": feature_form_temp_goal,
            "feature_form_temp_challenges": feature_form_temp_challenges,
            "feature_form_temp_use_case": feature_form_temp_use_case,
            "feature_form_temp_area": feature_form_temp_area,
            "feature_form_temp_criteria": feature_form_temp_criteria,
            "feature_form_temp_priority": feature_form_temp_priority,
        })

        # Build chat_description JSON
        chat_description = json.dumps({
            "feature_challenges": feature_challenges,
            "feature_use_case": feature_use_case,
            "feature_target_area": feature_target_area,
            "feature_goal": feature_goal,
            "feature_criteria": feature_criteria,
            "feature_priority": feature_priority,
            "feature_description": feature_description,
            "user_story": user_story
        })

        sender_id = tracker.sender_id

        if tracker.get_slot("zz_confirm_form") == "yes":

            # Establish database connection
            conn = self.get_db_connection()
            if conn is not None:
                cursor = conn.cursor()
                try:
                    # Insert data into the database
                    query = """
                        INSERT INTO chatbot_results (sender_id, user_story, initial_description, chat_description, createdAt, updatedAt)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(query, (
                    sender_id, user_story, initial_description, chat_description, datetime.now(), datetime.now()))
                    conn.commit()
                    dispatcher.utter_message(response="utter_feedback_received")
                except Exception as e:
                    print("Failed to insert into database:", e)
                    dispatcher.utter_message(text="Failed to save feature request.")
                finally:
                    cursor.close()
                    conn.close()
        else:
            # Respond if user selects No to send feedback
            dispatcher.utter_message(response="utter_feedback_cancelled")

        return [SlotSet(slot, tracker.get_slot(slot)) for slot in [
            "feature_challenges", "feature_use_case", "feature_target_area",
            "feature_goal", "feature_criteria", "feature_priority",
            "feature_description", "user_story"]]

class ActionBugReport(Action):
    """Report bug and errors."""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_bug_report"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Executes the action"""

        # Initialize the slots to be reset
        slots = {
            "AA_CONTINUE_FORM": None,
            "zz_confirm_form": None,
            "request_subject": None,
            "bug_description": None,
        }

        if tracker.get_slot("zz_confirm_form") == "yes":
            # Retrieve the report subject and bug description slots
            request_subject = tracker.get_slot("request_subject")
            bug_description = tracker.get_slot("bug_description")
            # Log the bug report details
            print("Bug report made: " + request_subject + ": " + bug_description)
            # Notify the user that the feedback has been received
            dispatcher.utter_message(response="utter_feedback_received")
        else:
            # Notify the user that the feedback has been cancelled
            dispatcher.utter_message(response="utter_feedback_cancelled")

        # Reset the slots and return them
        return [SlotSet(slot, value) for slot, value in slots.items()]

class ActionGenericComment(Action):
    """Provide generic comment."""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_generic_comment"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict]:
        """Executes the action"""

        # Initialize the slots to be reset
        slots = {
            "AA_CONTINUE_FORM": None,
            "zz_confirm_form": None,
            "request_subject": None,
            "comment_description": None,
        }

        if tracker.get_slot("zz_confirm_form") == "yes":
            # Retrieve the comment subject and comment description slots
            request_subject = tracker.get_slot("request_subject")
            comment_description = tracker.get_slot("comment_description")
            # Log the comment or feedback details
            print("Comment or feedback made: " + request_subject + ": " + comment_description)
            # Notify the user that the feedback has been received
            dispatcher.utter_message(response="utter_feedback_received")
        else:
            # Notify the user that the feedback has been cancelled
            dispatcher.utter_message(response="utter_feedback_cancelled")

        # Reset the slots and return them
        return [SlotSet(slot, value) for slot, value in slots.items()]


class ActionSessionStart(Action):
    """Executes at start of session"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_session_start"

    @staticmethod
    def _slot_set_events_from_tracker(
            tracker: "Tracker",
    ) -> List["SlotSet"]:
        """Fetches SlotSet events from tracker and carries over keys and values"""

        # List of slots to be carried over when restarting
        relevant_slots = [
            "AA_CONTINUE_FORM",
            "feature_description",
            "bug_description",
            "comment_description",
            "zz_confirm_form"]

        return [
            SlotSet(
                key=event.get("name"),
                value=event.get("value"),
            )
            for event in tracker.events
            if event.get("event") == "slot" and event.get("name") in relevant_slots
        ]

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[EventType]:
        """Executes the custom action"""

        # The session should begin with a `session_started` event
        events = [SessionStarted()]

        # Extend the event list with slot set events carried over from the tracker
        events.extend(self._slot_set_events_from_tracker(tracker))

        # Add `action_listen` at the end to listen for the next user input
        events.append(ActionExecuted("action_listen"))

        return events

class ActionRestart(Action):
    """Executes after restart of a session"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_restart"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[EventType]:
        """Executes the custom action"""

        # Return a list of events: Restarted and a follow-up action to start the session
        return [Restarted(), FollowupAction("action_session_start")]

class ActionSwitchFormsAsk(Action):
    """Asks to switch forms"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_switch_forms_ask"

    async def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        print("Inside ActionSwitchFormsAsk...")

        # Mappings of intents to form names
        intent_to_form = {
            "provide_feature_request": "feature_request_form",
            "provide_bug_report": "bug_report_form",
            "provide_generic_comment": "generic_comment_form",
        }

        # Descriptions for forms
        form_descriptions = {
            "feature_request_form": "Feature Request Form",
            "bug_report_form": "Bug Report Form",
            "generic_comment_form": "Generic Comment Form",
        }

        # Get the name of the currently active form
        active_form_name = tracker.active_loop.get("name")
        # Get the name of the intent from the latest message
        intent_name = tracker.latest_message["intent"]["name"]
        # Map the intent to the corresponding form name
        next_form_name = intent_to_form.get(intent_name)

        if (
                active_form_name not in form_descriptions
                or next_form_name not in form_descriptions
        ):
            # If the active form or next form name is not recognized, log a debug message
            logger.debug(
                f"Cannot create text for `active_form_name={active_form_name}` & "
                f"`next_form_name={next_form_name}`"
            )
            next_form_name = None
        else:
            # Create a prompt asking if the user wants to switch forms
            text = (
                f"We haven't completed the {form_descriptions[active_form_name]} yet. "
                f"Are you sure you want to switch to {form_descriptions[next_form_name]}?"
            )
            buttons = [
                {"payload": "/affirm", "title": "Yes"},
                {"payload": "/deny", "title": "No"},
            ]
            # Send the prompt with buttons to the user
            dispatcher.utter_message(text=text, buttons=buttons)

        # Return the event to set the next form name slot
        return [SlotSet("next_form_name", next_form_name)]

class ActionSwitchFormsDeny(Action):
    """Does not switch forms"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_switch_forms_deny"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""
        print("Inside ActionSwitchFormsDeny...")

        # Get the name of the currently active form
        active_form_name = tracker.active_loop.get("name")

        if active_form_name not in FORM_DESCRIPTION.keys():
            # If the active form name is not recognized, log a debug message
            logger.debug(
                f"Cannot create text for `active_form_name={active_form_name}`."
            )
        else:
            # Inform the user that the current form will continue
            text = f"Ok, let's continue with the {FORM_DESCRIPTION[active_form_name]}."
            dispatcher.utter_message(text=text)

        # Return the event to reset the next form name slot
        return [SlotSet("next_form_name", None)]


class ActionSwitchFormsAffirm(Action):
    """Switches forms"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_switch_forms_affirm"

    async def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""

        # Get the name of the currently active form
        active_form_name = tracker.active_loop.get("name")
        # Get the name of the next form to switch to
        next_form_name = tracker.get_slot("next_form_name")

        if (
                active_form_name not in FORM_DESCRIPTION.keys()
                or next_form_name not in FORM_DESCRIPTION.keys()
        ):
            # If either the active form or next form name is not recognized, log a debug message
            logger.debug(
                f"Cannot create text for `active_form_name={active_form_name}` & "
                f"`next_form_name={next_form_name}`"
            )
        else:
            # Inform the user that the form will be switched
            text = (
                f"Great. Let's switch from the {FORM_DESCRIPTION[active_form_name]} "
                f"to {FORM_DESCRIPTION[next_form_name]}. "
                f"Once completed, you will have the option to switch back."
            )
            dispatcher.utter_message(text=text)

        # Return events to set the previous form name and reset the next form name slot
        return [
            SlotSet("previous_form_name", active_form_name),
            SlotSet("next_form_name", None),
        ]

class ActionSwitchBackAsk(Action):
    """Asks to switch back to previous form"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "action_switch_back_ask"

    async def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Executes the custom action"""

        # Get the name of the previous form
        previous_form_name = tracker.get_slot("previous_form_name")

        if previous_form_name not in FORM_DESCRIPTION.keys():
            # If the previous form name is not recognized, log a debug message
            logger.debug(
                f"Cannot create text for `previous_form_name={previous_form_name}`"
            )
            previous_form_name = None
        else:
            # Create a prompt asking if the user wants to switch back to the previous form
            text = (
                f"Would you like to go back to the "
                f"{FORM_DESCRIPTION[previous_form_name]} now?."
            )
            buttons = [
                {"payload": "/affirm", "title": "Yes"},
                {"payload": "/deny", "title": "No"},
            ]
            # Send the prompt with buttons to the user
            dispatcher.utter_message(text=text, buttons=buttons)

        # Return the event to reset the previous form name slot
        return [SlotSet("previous_form_name", None)]

class ValidateRequestFeatureForm(CustomFormValidationAction):
    """Validates Slots of the request_feature_form"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "validate_feature_request_form"

    async def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Custom validates the filled slots"""

        events = await super().run(dispatcher, tracker, domain)

        # First check if AA_CONTINUE_FORM is not None
        if tracker.get_slot("AA_CONTINUE_FORM") is None:
            # Return an empty list of events or re-prompt for AA_CONTINUE_FORM as needed
            return [SlotSet("requested_slot", "AA_CONTINUE_FORM")]

        # If user answers /deny, exit the form loop
        if tracker.get_slot("AA_CONTINUE_FORM") == "no":
            print("Checking AA_CONTINUE_FORM")
            return [SlotSet("AA_CONTINUE_FORM", None), SlotSet("requested_slot", None), ActiveLoop(None)]

        # Validate each slot and prepare messages if necessary
        required_slots = [
            "bb_request_description",
            "feature_challenges",
            "feature_use_case",
            "feature_target_area",
            "feature_goal",
            "feature_criteria",
            "feature_priority",
            "feature_description",
        ]

        for slot_name in required_slots:
            slot_value = tracker.get_slot(slot_name)
            if not slot_value:  # Check if the slot is filled
                # Set the slot to request the user to fill it if it is empty
                events.append(SlotSet("requested_slot", slot_name))
                # Send message to the user prompting for this specific slot
                break  # Break after the first empty slot is found

        return events

    def validate_bb_request_description(
            self,
            slot_value: Any,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate `bb_request_description` value."""

        # Get slot value
        user_description = slot_value

        # LLM prompt instructions to analyze and identify possible fields from user's initial message.
        prompt_instruction = """
            Based on user's description, identify and extract the distinct components related to a feature request. The response should be formatted as JSON with the following fields:
            - 'goal_and_objective': The main purpose and expected outcome of the feature.
            - 'pain_points_and_challenges': Specific problems or frustrations the user is currently experiencing that the new feature should address.
            - 'use_case': How the user envisions using the new feature, including specific actions or capabilities needed.
            - 'target_area': The target part of the software where the new feature should be implemented or integrated.
            - 'acceptance_criteria': Conditions for the feature to be considered complete and successful, and how it will be tested and validated.
            - 'priority_and_urgency': The importance of the feature compared to other tasks, and any specific timeline or deadline for its implementation.

            Each field should contain the relevant extracted information, however try to keep it as short as possible and no need for complete sentences. 
            If any information is not provided by the user, leave the field empty. Here is the structure to follow:

            {
                \"goal_and_objective\": \"\",
                \"pain_points_and_challenges\": \"\",
                \"use_case\": \"\",
                \"target_area\": \"\",
                \"acceptance_criteria\": \"\",
                \"priority_and_urgency\": \"\"
            }

            Please provide the extracted information in the above JSON format.
            """
        message_text = [
            {"role": "system", "content": prompt_instruction},
            {"role": "user", "content": user_description},
        ]

        try:
            # Request completion from Azure OpenAI
            completion = client.chat.completions.create(
                model="gpt-35-fallback",  # Use the appropriate model
                messages=message_text,
                temperature=0.7,
                max_tokens=800,
                top_p=0.95,
                frequency_penalty=0,
                presence_penalty=0,
                stop=None
            )

            response = completion.choices[0].message.content
            print(response)  # Print the response for debugging

            # Parse the JSON response
            extracted_data = json.loads(response)

            print(extracted_data)
            # Ensure all keys are present in the parsed data, if non-existing then add to the keys
            required_keys = ["goal_and_objective", "pain_points_and_challenges", "use_case", "target_area",
                             "acceptance_criteria", "priority_and_urgency"]
            for key in required_keys:
                if key not in extracted_data:
                    extracted_data[key] = ""

            # Returning request description and LLM generated parts in temporary slots
            return {
                "bb_request_description": slot_value,
                "feature_form_temp_goal": extracted_data["goal_and_objective"],
                "feature_form_temp_challenges": extracted_data["pain_points_and_challenges"],
                "feature_form_temp_use_case": extracted_data["use_case"],
                "feature_form_temp_area": extracted_data["target_area"],
                "feature_form_temp_criteria": extracted_data["acceptance_criteria"],
                "feature_form_temp_priority": extracted_data["priority_and_urgency"],
                "feature_form_temp_goal_ident": bool(extracted_data["goal_and_objective"]),
                "feature_form_temp_challenges_ident": bool(extracted_data["pain_points_and_challenges"]),
                "feature_form_temp_use_case_ident": bool(extracted_data["use_case"]),
                "feature_form_temp_area_ident": bool(extracted_data["target_area"]),
                "feature_form_temp_criteria_ident": bool(extracted_data["acceptance_criteria"]),
                "feature_form_temp_priority_ident": bool(extracted_data["priority_and_urgency"])
            }

        except Exception as e:
            dispatcher.utter_message(text="There was an error processing your request. Please try again.")
            return {"bb_request_description": None}

    def validate_feature_description(
            self,
            slot_value: Any,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate `feature_description` value."""

        # Get slot values
        bb_request_description = tracker.get_slot("bb_request_description")
        feature_challenges = tracker.get_slot("feature_challenges")
        feature_goal = tracker.get_slot("feature_goal")
        feature_use_case = tracker.get_slot("feature_use_case")
        feature_target_area = tracker.get_slot("feature_target_area")
        feature_criteria = tracker.get_slot("feature_criteria")
        feature_priority = tracker.get_slot("feature_priority")
        feature_description = slot_value

        feature_form_temp_challenges = tracker.get_slot("feature_form_temp_challenges")
        feature_form_temp_goal = tracker.get_slot("feature_form_temp_goal")
        feature_form_temp_use_case = tracker.get_slot("feature_form_temp_use_case")
        feature_form_temp_area = tracker.get_slot("feature_form_temp_area")
        feature_form_temp_criteria = tracker.get_slot("feature_form_temp_criteria")
        feature_form_temp_priority = tracker.get_slot("feature_form_temp_priority")

        # Once user enters text for final description field, then all relevant fields are sent to LLM to
        # generate a suggested user story before user's final confirmation.
        message_text = [
            {
                "role": "user",
                "content": (
                    f"Given below components, generate a user story. Return user story within 1-2 sentence and provide "
                    f"no explanations. The fields after initial description are secondary as fields before that take precedent."
                    f"Pain points and challenges to resolve: {feature_challenges}\n"
                    f"Goal and objectives: {feature_goal}\n"
                    f"Use case and functionality: {feature_use_case}\n"
                    f"Target area or section: {feature_target_area}\n"
                    f"Priority: {feature_priority}\n"
                    f"Criteria for acceptance or completion: {feature_criteria}\n"
                    f"Description: {feature_description}\n"

                    "Below are user's initial description and identified temporary components:\n"
                    f"Initial description: {bb_request_description}\n"
                    f"Pain points and challenges to resolve: {feature_form_temp_challenges}\n"
                    f"Goal and objectives: {feature_form_temp_goal}\n"
                    f"Use case and functionality: {feature_form_temp_use_case}\n"
                    f"Target area or section: {feature_form_temp_area}\n"
                    f"Criteria: {feature_form_temp_criteria}\n"
                    f"Feature priority: {feature_form_temp_priority}\n"
                ),
            },
        ]

        completion = client.chat.completions.create(
            model="gpt-35-fallback",  # "deployment_name"
            messages=message_text,
            temperature=0.7,
            max_tokens=800,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
        )

        generated_user_story = completion.choices[0].message.content

        # If the description is too short, return a None slot to re-prompt.
        if len(slot_value) < 2:
            dispatcher.utter_message(text="Description must be at least 2 character.")
            return {"feature_description": None}

        # Setting the 'user_story' slot
        return {
            "feature_description": slot_value,
            "user_story": generated_user_story  # Now this slot change will be effectively returned
        }

    def validate_user_story(
            self,
            slot_value: Any,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate `user_story` slot based on specific conditions."""

        current_user_story = tracker.get_slot("user_story")

        # Check if the response is either "/affirm" or "/deny"
        if slot_value in ["/affirm", "/deny"]:
            return {"user_story": current_user_story}

        # Validate the new user story length
        if len(slot_value) <= 3:
            dispatcher.utter_message(text="User story must be at least 4 characters.")
            return {"user_story": current_user_story}

        # Accept new value if it is longer than 3 characters and not "/affirm" or "/deny"
        return {"user_story": slot_value}

    async def validate_zz_confirm_form(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'zz_confirm_form' slot"""
        if value in ["yes", "no"]:
            return {"zz_confirm_form": value}

        return {"zz_confirm_form": None}

class ValidateBugReportForm(CustomFormValidationAction):
    """Validates Slots of the bug_report"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "validate_bug_report_form"

    async def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Custom validates the filled slots"""
        events = await super().run(dispatcher, tracker, domain)

        # For 'spend' type transactions we need to know the vendor_name
        request_subject = tracker.get_slot("request_subject")
        if request_subject:
            bug_description = tracker.get_slot("bug_description")
            if not bug_description:
                # Request the bug_description slot if it is not filled
                events.append(SlotSet("requested_slot", "bug_description"))

        return events

    async def validate_zz_confirm_form(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'zz_confirm_form' slot"""
        if value in ["yes", "no"]:
            return {"zz_confirm_form": value}

        return {"zz_confirm_form": None}


class ValidateGenericCommentForm(CustomFormValidationAction):
    """Validates Slots of the generic_comment_form"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "validate_generic_comment_form"

    async def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Custom validates the filled slots"""
        events = await super().run(dispatcher, tracker, domain)

        # Check if request_subject slot is filled
        request_subject = tracker.get_slot("request_subject")
        if request_subject:
            # Check if comment_description slot is filled
            comment_description = tracker.get_slot("comment_description")
            if not comment_description:
                # Request the comment_description slot if it is not filled
                events.append(SlotSet("requested_slot", "comment_description"))

        return events

    async def validate_zz_confirm_form(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'zz_confirm_form' slot"""
        if value in ["yes", "no"]:
            return {"zz_confirm_form": value}

        return {"zz_confirm_form": None}


class ValidateGenericCommentForm(CustomFormValidationAction):
    """Validates Slots of the generic_comment_form"""

    def name(self) -> Text:
        """Unique identifier of the action"""
        return "validate_generic_comment_form"

    async def run(
            self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict
    ) -> List[EventType]:
        """Custom validates the filled slots"""
        events = await super().run(dispatcher, tracker, domain)

        # Check if request_subject slot is filled
        request_subject = tracker.get_slot("request_subject")
        if request_subject:
            # Check if comment_description slot is filled
            comment_description = tracker.get_slot("comment_description")
            if not comment_description:
                # Request the comment_description slot if it is not filled
                events.append(SlotSet("requested_slot", "comment_description"))

        return events

    async def validate_zz_confirm_form(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:
        """Validates value of 'zz_confirm_form' slot"""
        if value in ["yes", "no"]:
            return {"zz_confirm_form": value}

        return {"zz_confirm_form": None}

