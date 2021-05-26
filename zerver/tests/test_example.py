from typing import Any, List, Mapping

import orjson

from zerver.lib.actions import do_change_can_create_users, do_change_user_role
from zerver.lib.exceptions import JsonableError
from zerver.lib.streams import access_stream_for_send_message
from zerver.lib.test_classes import ZulipTestCase
from zerver.lib.test_helpers import most_recent_message, queries_captured
from zerver.lib.users import is_administrator_role
from zerver.models import (
    UserProfile,
    UserStatus,
    get_display_recipient,
    get_realm,
    get_stream,
    get_user_by_delivery_email,
)


# Most Zulip tests use ZulipTestCase, which inherits from django.test.TestCase.
# We recommend learning Django basics first, so search the web for "django testing".
# A common first result is https://docs.djangoproject.com/en/3.2/topics/testing/
class TestBasics(ZulipTestCase):
    def test_basics(self) -> None:
        # Django's tests are based on Python's unittest module, so you
        # will see us use things like assertEqual, assertTrue, and assertRaisesRegex
        # quite often.
        # See https://docs.python.org/3/library/unittest.html#unittest.TestCase.assertEqual
        self.assertEqual(7 * 6, 42)


class TestBasicUserStuff(ZulipTestCase):
    # Zulip has test fixtures with built-in users.  It's good to know
    # which users are special. For example, Iago is our built-in
    # realm administrator.  You can also modify users as needed.
    def test_users(self) -> None:
        # The example_user() helper returns a UserProfile object.
        hamlet = self.example_user("hamlet")
        self.assertEqual(hamlet.full_name, "King Hamlet")
        self.assertEqual(hamlet.role, UserProfile.ROLE_MEMBER)

        iago = self.example_user("iago")
        self.assertEqual(iago.role, UserProfile.ROLE_REALM_ADMINISTRATOR)

        polonius = self.example_user("polonius")
        self.assertEqual(polonius.role, UserProfile.ROLE_GUEST)

        self.assertEqual(self.example_email("cordelia"), "cordelia@zulip.com")

    def test_lib_functions(self) -> None:
        # This test is an example of testing a single library function.
        # Our tests aren't always at this level of granularity, but it's
        # often possible to write concise tests for library functions.

        # Get our UserProfile objects first.
        iago = self.example_user("iago")
        hamlet = self.example_user("hamlet")

        # It is a good idea for your tests to clearly demonstrate a
        # **change** to a value.  So here we want to make sure that
        # do_change_user_role will change Hamlet such that
        # is_administrator_role becomes True, but we first assert it's
        # False.
        self.assertFalse(is_administrator_role(hamlet.role))

        do_change_user_role(hamlet, UserProfile.ROLE_REALM_OWNER, acting_user=iago)
        self.assertTrue(is_administrator_role(hamlet.role))

        # After we promote Hamlet, we also demote him.  Testing state
        # changes like this in a single test can be a good technique,
        # although we also don't want tests to be too long.
        do_change_user_role(hamlet, UserProfile.ROLE_MODERATOR, acting_user=iago)
        self.assertFalse(is_administrator_role(hamlet.role))


class TestFullStack(ZulipTestCase):
    # A lot of Zulip's unit tests are actually somewhat full-stack in
    # nature, and some folks might consider them to be more like "integration"
    # tests. Django makes it pretty easy to test Zulip endpoints, and then
    # ZulipTestCase has some additional helpers.
    def test_client_get(self) -> None:
        hamlet = self.example_user("hamlet")
        cordelia = self.example_user("cordelia")

        # Most full-stack tests require you to log in the user.
        # The login_user helper basically wraps Django's client.login().
        self.login_user(hamlet)

        # Zulip's client_get is a very thin wrapper on Django's client.get.
        # We always use the Zulip wrappers for client_get and client_post.
        url = f"/json/users/{cordelia.id}"
        result = self.client_get(url)

        # Almost every meaningful full-stack test for a "happy path" situation
        # uses assert_json_success().
        self.assert_json_success(result)

        # When we unpack the result.content object, we prefer the orjson library.
        content = orjson.loads(result.content)

        # In this case we will validate the entire payload. It's good to use
        # concrete values where possible, but some things, like "cordelia.id",
        # are somewhat unpredictable, so we don't hard code values.
        self.assertEqual(
            content["user"],
            dict(
                avatar_url=content["user"]["avatar_url"],
                avatar_version=1,
                date_joined=content["user"]["date_joined"],
                email=cordelia.email,
                full_name="Cordelia, Lear's daughter",
                is_active=True,
                is_admin=False,
                is_billing_admin=False,
                is_bot=False,
                is_guest=False,
                is_owner=False,
                role=UserProfile.ROLE_MEMBER,
                timezone="",
                user_id=cordelia.id,
            ),
        )

    def test_client_post(self) -> None:
        # Here we're gonna test a POST call to /json/users, and it's
        # important that we not only check the payload, but we make
        # sure that the intended side effects actually happen.
        iago = self.example_user("iago")
        self.login_user(iago)

        realm = get_realm("zulip")
        self.assertEqual(realm.id, iago.realm_id)

        # Get our failing test first.
        self.assertRaises(
            UserProfile.DoesNotExist, lambda: get_user_by_delivery_email("romeo@zulip.net", realm)
        )

        # Before we can successfully post, we need to ensure
        # that Iago can create users.
        do_change_can_create_users(iago, True)

        params = dict(
            email="romeo@zulip.net",
            password="xxxx",
            full_name="Romeo Montague",
        )

        # Use the Zulip wrapper.
        result = self.client_post("/json/users", params)

        # Once again we check that the HTTP request was successful.
        self.assert_json_success(result)
        content = orjson.loads(result.content)

        # Finally we test the side effect of the post.
        user_id = content["user_id"]
        romeo = get_user_by_delivery_email("romeo@zulip.net", realm)
        self.assertEqual(romeo.id, user_id)

    def test_errors(self) -> None:
        iago = self.example_user("iago")
        self.login_user(iago)

        do_change_can_create_users(iago, False)
        params = dict(
            email="romeo@zulip.net",
            password="xxxx",
            full_name="Romeo Montague",
        )

        # We often use assert_json_error for negative tests.
        result = self.client_post("/json/users", params)
        self.assert_json_error(result, "User not authorized for this query", 400)

        do_change_can_create_users(iago, True)
        params = dict(
            full_name="Romeo Montague",
        )
        result = self.client_post("/json/users", params)
        self.assert_json_error(result, "Missing 'email' argument", 400)

    def test_tornado_redirects(self) -> None:
        # Let's poke a bit at Zulip's event system.
        # See https://zulip.readthedocs.io/en/latest/subsystems/events-system.html
        # for context on the system itself.
        cordelia = self.example_user("cordelia")
        self.login_user(cordelia)

        params = dict(status_text="on vacation")

        events: List[Mapping[str, Any]] = []

        # Use the tornado_redirected_to_list context manager to capture
        # events.
        with self.tornado_redirected_to_list(events, expected_num_events=1):
            result = self.api_post(cordelia, "/api/v1/users/me/status", params)

        self.assert_json_success(result)

        # Check that the POST to Zulip causes the correct events to be sent
        # to Tornado.
        self.assertEqual(
            events[0]["event"],
            dict(type="user_status", user_id=cordelia.id, status_text="on vacation"),
        )

        row = UserStatus.objects.last()
        self.assertEqual(row.user_profile_id, cordelia.id)
        self.assertEqual(row.status_text, "on vacation")


class TestStreamHelpers(ZulipTestCase):
    # Streams are an important concept in Zulip, and ZulipTestCase
    # has helpers such as subscribe, users_subscribed_to_stream,
    # and make_stream.
    def test_new_streams(self) -> None:
        cordelia = self.example_user("cordelia")
        othello = self.example_user("othello")
        realm = cordelia.realm

        stream_name = "Some new stream"
        self.subscribe(cordelia, stream_name)

        self.assertEqual(set(self.users_subscribed_to_stream(stream_name, realm)), {cordelia})

        self.subscribe(othello, stream_name)
        self.assertEqual(
            set(self.users_subscribed_to_stream(stream_name, realm)), {cordelia, othello}
        )

    def test_private_stream(self) -> None:
        # When we test stream permissions, it's very common to use at least
        # two users, so that you can see how different users are impacted.
        # We commonly use Othello to represent the "other" user from the primary user.
        cordelia = self.example_user("cordelia")
        othello = self.example_user("othello")

        realm = cordelia.realm
        stream_name = "Some private stream"

        # Use the invite_only flag in make_stream to make a stream "private".
        stream = self.make_stream(stream_name=stream_name, invite_only=True)
        self.subscribe(cordelia, stream_name)

        self.assertEqual(set(self.users_subscribed_to_stream(stream_name, realm)), {cordelia})

        stream = get_stream(stream_name, realm)
        self.assertEqual(stream.name, stream_name)
        self.assertTrue(stream.invite_only)

        # We will now observe that Cordelia can access the stream...
        access_stream_for_send_message(cordelia, stream, forwarder_user_profile=None)

        # ...but Othello can't.
        msg = "Not authorized to send to stream"
        with self.assertRaisesRegex(JsonableError, msg):
            access_stream_for_send_message(othello, stream, forwarder_user_profile=None)


class TestMessageHelpers(ZulipTestCase):
    # If you are testing behavior related to messages, then it's good
    # to know about send_stream_message, send_personal_message, and
    # most_recent_message.
    def test_stream_message(self) -> None:
        hamlet = self.example_user("hamlet")
        iago = self.example_user("iago")
        self.subscribe(hamlet, "Denmark")
        self.subscribe(iago, "Denmark")

        self.send_stream_message(
            sender=hamlet,
            stream_name="Denmark",
            topic_name="lunch",
            content="I want pizza!",
        )

        iago_message = most_recent_message(iago)

        self.assertEqual(iago_message.sender_id, hamlet.id)
        self.assertEqual(get_display_recipient(iago_message.recipient), "Denmark")
        self.assertEqual(iago_message.topic_name(), "lunch")
        self.assertEqual(iago_message.content, "I want pizza!")

    def test_personal_message(self) -> None:
        hamlet = self.example_user("hamlet")
        cordelia = self.example_user("cordelia")

        self.send_personal_message(
            from_user=hamlet,
            to_user=cordelia,
            content="hello there!",
        )

        cordelia_message = most_recent_message(cordelia)

        self.assertEqual(cordelia_message.sender_id, hamlet.id)
        self.assertEqual(cordelia_message.content, "hello there!")


class TestQueryCounts(ZulipTestCase):
    def test_capturing_queries(self) -> None:
        # It's a common pitfall in Django to have your app perform
        # too many queries due to lazy evaluation. We use the queries_captured
        # context manager to ensure our query count is predictable.
        hamlet = self.example_user("hamlet")
        cordelia = self.example_user("cordelia")

        with queries_captured() as queries:
            self.send_personal_message(
                from_user=hamlet,
                to_user=cordelia,
                content="hello there!",
            )

        # The assert_length helper is another useful extra from ZulipTestCase.
        self.assert_length(queries, 16)
