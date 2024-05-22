import pytest

from rasa_sdk.executor import CollectingDispatcher, Tracker
from rasa_sdk.events import SlotSet, ActionExecuted, SessionStarted

from actions.actions import ActionSessionStart, ActionCheckMongolianGreeting, ActionProvidePageInfo, ActionRequestFeature, ActionBugReport, ActionGenericComment

@pytest.mark.asyncio
async def test_run_action_session_start(dispatcher, domain):
    tracker = Tracker(
        sender_id="test_user",
        slots={},
        latest_message={},
        events=[],
        paused=False,
        followup_action=None,
        active_loop={"name": None},
        latest_action_name="action_listen",
    )
    action = ActionSessionStart()
    events = await action.run(dispatcher, tracker, domain)
    expected_events = [
        SessionStarted(),
        ActionExecuted("action_listen"),
    ]
    assert events == expected_events

@pytest.mark.asyncio
async def test_run_action_check_mongolian_greeting(dispatcher, domain):
    tracker = Tracker(
        sender_id="test_user",
        slots={"mongolian_greeting_used": None},
        latest_message={"text": "Сайн байна уу"},
        events=[],
        paused=False,
        followup_action=None,
        active_loop={"name": None},
        latest_action_name="action_listen",
    )
    action = ActionCheckMongolianGreeting()
    events = await action.run(dispatcher, tracker, domain)
    expected_events = [SlotSet("mongolian_greeting_used", True)]
    assert events == expected_events

@pytest.mark.asyncio
async def test_run_action_provide_page_info(dispatcher, domain):
    tracker = Tracker(
        sender_id="test_user",
        slots={"page": "calculator"},
        latest_message={"text": "find the calculator page"},
        events=[],
        paused=False,
        followup_action=None,
        active_loop={"name": None},
        latest_action_name="action_listen",
    )
    action = ActionProvidePageInfo()
    events = await action.run(dispatcher, tracker, domain)
    expected_events = []
    assert events == expected_events
    dispatcher.utter_message.assert_called_once_with(
        text="Here is the information you requested: <a target='_new' href='https://becs.e-nomads.com/calculator' >https://becs.e-nomads.com/calculator</a>"
    )

@pytest.mark.asyncio
async def test_run_action_request_feature(dispatcher, domain):
    tracker = Tracker(
        sender_id="test_user",
        slots={
            "bb_request_description": "Need a new feature",
            "feature_form_temp_goal": "Improve user experience",
            "feature_form_temp_challenges": "Current system is slow",
            "feature_form_temp_use_case": "User needs faster access",
            "feature_form_temp_area": "Dashboard",
            "feature_form_temp_criteria": "Response time < 2s",
            "feature_form_temp_priority": "High",
            "zz_confirm_form": "yes"
        },
        latest_message={"text": "I need a new feature"},
        events=[],
        paused=False,
        followup_action=None,
        active_loop={"name": None},
        latest_action_name="action_listen",
    )
    action = ActionRequestFeature()
    events = await action.run(dispatcher, tracker, domain)
    expected_events = [
        SlotSet("feature_challenges", None),
        SlotSet("feature_use_case", None),
        SlotSet("feature_target_area", None),
        SlotSet("feature_goal", None),
        SlotSet("feature_criteria", None),
        SlotSet("feature_priority", None),
        SlotSet("feature_description", None),
        SlotSet("user_story", None)
    ]
    assert events == expected_events

@pytest.mark.asyncio
async def test_run_action_bug_report(dispatcher, domain):
    tracker = Tracker(
        sender_id="test_user",
        slots={
            "request_subject": "Bug in the system",
            "bug_description": "System crashes frequently",
            "zz_confirm_form": "yes"
        },
        latest_message={"text": "I found a bug"},
        events=[],
        paused=False,
        followup_action=None,
        active_loop={"name": None},
        latest_action_name="action_listen",
    )
    action = ActionBugReport()
    events = await action.run(dispatcher, tracker, domain)
    expected_events = [
        SlotSet("AA_CONTINUE_FORM", None),
        SlotSet("zz_confirm_form", None),
        SlotSet("request_subject", None),
        SlotSet("bug_description", None)
    ]
    assert events == expected_events

@pytest.mark.asyncio
async def test_run_action_generic_comment(dispatcher, domain):
    tracker = Tracker(
        sender_id="test_user",
        slots={
            "request_subject": "General feedback",
            "comment_description": "Great job!",
            "zz_confirm_form": "yes"
        },
        latest_message={"text": "I have some feedback"},
        events=[],
        paused=False,
        followup_action=None,
        active_loop={"name": None},
        latest_action_name="action_listen",
    )
    action = ActionGenericComment()
    events = await action.run(dispatcher, tracker, domain)
    expected_events = [
        SlotSet("AA_CONTINUE_FORM", None),
        SlotSet("zz_confirm_form", None),
        SlotSet("request_subject", None),
        SlotSet("comment_description", None)
    ]
    assert events == expected_events
