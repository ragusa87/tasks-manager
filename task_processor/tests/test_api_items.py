import json
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone
from ninja.errors import HttpError

from task_processor.api.items import create_item
from task_processor.api.schemas import ItemIn
from task_processor.constants import GTDStatus, Priority
from task_processor.models import ApiKey, Area, Context, Item, Tag


class TestCreateItemUnit(TestCase):
    """Unit tests for the HTTP-free create_item() function."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )

    def test_minimal_payload_uses_defaults(self):
        item = create_item(self.user, ItemIn(title="Buy milk"))
        self.assertEqual(item.user, self.user)
        self.assertEqual(item.status, GTDStatus.INBOX)
        self.assertEqual(item.priority, Priority.NORMAL)
        self.assertEqual(item.tags.count(), 0)
        self.assertEqual(item.contexts.count(), 0)

    def test_full_payload_sets_relations(self):
        parent = Item.objects.create(
            title="Groceries", status=GTDStatus.PROJECT, user=self.user
        )
        area = Area.objects.create(name="Personal", user=self.user)
        tag = Tag.objects.create(name="errand", user=self.user)
        context = Context.objects.create(name="home", user=self.user)

        item = create_item(
            self.user,
            ItemIn(
                title="Buy milk",
                status=GTDStatus.NEXT_ACTION,
                parent_id=parent.id,
                area_id=area.id,
                tag_ids=[tag.id],
                context_ids=[context.id],
            ),
        )
        self.assertEqual(item.parent, parent)
        self.assertEqual(item.area, area)
        self.assertEqual(list(item.tags.all()), [tag])
        self.assertEqual(list(item.contexts.all()), [context])

    def test_foreign_user_tag_raises_422(self):
        tag = Tag.objects.create(name="errand", user=self.other_user)
        with self.assertRaises(HttpError):
            create_item(self.user, ItemIn(title="Buy milk", tag_ids=[tag.id]))

    def test_foreign_user_area_raises_422(self):
        area = Area.objects.create(name="Personal", user=self.other_user)
        with self.assertRaises(HttpError):
            create_item(self.user, ItemIn(title="Buy milk", area_id=area.id))

    def test_foreign_user_context_raises_422(self):
        context = Context.objects.create(name="home", user=self.other_user)
        with self.assertRaises(HttpError):
            create_item(self.user, ItemIn(title="Buy milk", context_ids=[context.id]))

    def test_foreign_user_parent_raises_422(self):
        parent = Item.objects.create(
            title="Groceries", status=GTDStatus.PROJECT, user=self.other_user
        )
        with self.assertRaises(HttpError):
            create_item(self.user, ItemIn(title="Buy milk", parent_id=parent.id))

    def test_non_project_parent_raises_422(self):
        parent = Item.objects.create(
            title="Some task", status=GTDStatus.NEXT_ACTION, user=self.user
        )
        with self.assertRaises(HttpError):
            create_item(self.user, ItemIn(title="Buy milk", parent_id=parent.id))

    def test_waiting_for_without_person_raises_422(self):
        with self.assertRaises(HttpError):
            create_item(
                self.user, ItemIn(title="Buy milk", status=GTDStatus.WAITING_FOR)
            )

    def test_nesting_beyond_max_depth_raises_422(self):
        root = Item.objects.create(
            title="Root", status=GTDStatus.PROJECT, user=self.user
        )
        child = Item.objects.create(
            title="Child", status=GTDStatus.PROJECT, user=self.user, parent=root
        )
        with self.assertRaises(HttpError):
            create_item(self.user, ItemIn(title="Too deep", parent_id=child.id))

    def test_naive_datetimes_are_made_aware(self):
        item = create_item(
            self.user,
            ItemIn(
                title="Buy milk",
                due_date=datetime(2030, 1, 1, 12, 0),
                start_date=datetime(2030, 1, 1, 9, 0),
                remind_at=datetime(2030, 1, 1, 8, 0),
            ),
        )
        self.assertTrue(timezone.is_aware(item.due_date))
        self.assertTrue(timezone.is_aware(item.start_date))
        self.assertTrue(timezone.is_aware(item.remind_at))

    def test_item_not_persisted_when_m2m_set_fails(self):
        with mock.patch.object(
            Item, "tags", new_callable=mock.PropertyMock, side_effect=RuntimeError
        ):
            with self.assertRaises(RuntimeError):
                create_item(self.user, ItemIn(title="Buy milk"))
        self.assertEqual(Item.objects.count(), 0)


class TestItemsEndpoint(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass"
        )
        _, self.raw_key = ApiKey.generate(self.user, "test key")
        self.headers = {"Authorization": f"Bearer {self.raw_key}"}

    def post_item(self, payload, headers=None):
        return self.client.post(
            "/api/items",
            data=json.dumps(payload),
            content_type="application/json",
            headers=self.headers if headers is None else headers,
        )

    def test_create_minimal_returns_201_with_defaults(self):
        response = self.post_item({"title": "Buy milk"})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["title"], "Buy milk")
        self.assertEqual(data["status"], GTDStatus.INBOX)
        self.assertEqual(data["priority"], Priority.NORMAL)
        self.assertEqual(data["tags"], [])
        self.assertEqual(data["contexts"], [])
        self.assertIsNone(data["area"])
        self.assertEqual(Item.objects.filter(user=self.user).count(), 1)

    def test_create_full_returns_201_with_nested_objects(self):
        parent = Item.objects.create(
            title="Groceries", status=GTDStatus.PROJECT, user=self.user
        )
        area = Area.objects.create(name="Personal", user=self.user)
        tag = Tag.objects.create(name="errand", user=self.user)
        context = Context.objects.create(name="home", user=self.user)
        due_date = (timezone.now() + timedelta(days=1)).isoformat()
        start_date = (timezone.now() + timedelta(hours=1)).isoformat()

        response = self.post_item(
            {
                "title": "Buy milk",
                "description": "2 liters",
                "status": GTDStatus.NEXT_ACTION,
                "priority": Priority.URGENT,
                "due_date": due_date,
                "start_date": start_date,
                "parent_id": parent.id,
                "area_id": area.id,
                "tag_ids": [tag.id],
                "context_ids": [context.id],
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["parent"], parent.id)
        self.assertEqual(data["area"]["id"], area.id)
        self.assertEqual(data["tags"], [{"id": tag.id, "name": "errand"}])
        self.assertEqual(data["contexts"][0]["id"], context.id)
        self.assertIsNotNone(data["due_date"])
        self.assertIsNotNone(data["start_date"])

    def test_blank_title_returns_422(self):
        response = self.post_item({"title": "   "})
        self.assertEqual(response.status_code, 422)

    def test_too_long_title_returns_422(self):
        response = self.post_item({"title": "x" * 1025})
        self.assertEqual(response.status_code, 422)

    def test_completed_status_returns_422(self):
        response = self.post_item({"title": "Buy milk", "status": GTDStatus.COMPLETED})
        self.assertEqual(response.status_code, 422)

    def test_cancelled_status_returns_422(self):
        response = self.post_item({"title": "Buy milk", "status": GTDStatus.CANCELLED})
        self.assertEqual(response.status_code, 422)

    def test_invalid_status_returns_422(self):
        response = self.post_item({"title": "Buy milk", "status": "not_a_status"})
        self.assertEqual(response.status_code, 422)

    def test_urgent_without_due_date_returns_422(self):
        response = self.post_item({"title": "Buy milk", "priority": Priority.URGENT})
        self.assertEqual(response.status_code, 422)

    def test_past_remind_at_returns_422(self):
        past = (timezone.now() - timedelta(days=1)).isoformat()
        response = self.post_item({"title": "Buy milk", "remind_at": past})
        self.assertEqual(response.status_code, 422)

    def test_unknown_tag_id_returns_422(self):
        response = self.post_item({"title": "Buy milk", "tag_ids": [999]})
        self.assertEqual(response.status_code, 422)

    def test_duplicate_tag_ids_are_deduplicated(self):
        tag = Tag.objects.create(name="errand", user=self.user)
        response = self.post_item({"title": "Buy milk", "tag_ids": [tag.id, tag.id]})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["tags"], [{"id": tag.id, "name": "errand"}])

    def test_foreign_area_id_returns_422(self):
        area = Area.objects.create(name="Personal", user=self.other_user)
        response = self.post_item({"title": "Buy milk", "area_id": area.id})
        self.assertEqual(response.status_code, 422)

    def test_unknown_parent_id_returns_422(self):
        response = self.post_item({"title": "Buy milk", "parent_id": 999})
        self.assertEqual(response.status_code, 422)

    def test_waiting_for_without_person_returns_422(self):
        response = self.post_item(
            {"title": "Buy milk", "status": GTDStatus.WAITING_FOR}
        )
        self.assertEqual(response.status_code, 422)

    def test_malformed_json_returns_400(self):
        response = self.client.post(
            "/api/items",
            data="{not json",
            content_type="application/json",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_without_auth_returns_401(self):
        response = self.post_item({"title": "Buy milk"}, headers={})
        self.assertEqual(response.status_code, 401)

    def test_list_returns_only_own_items(self):
        Item.objects.create(title="Mine", user=self.user)
        Item.objects.create(title="Not mine", user=self.other_user)
        response = self.client.get("/api/items", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        titles = [item["title"] for item in data["items"]]
        self.assertEqual(titles, ["Mine"])

    def test_list_empty_returns_200(self):
        response = self.client.get("/api/items", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [], "count": 0})

    def test_list_is_paginated(self):
        Item.objects.create(title="First", user=self.user)
        Item.objects.create(title="Second", user=self.user)
        response = self.client.get("/api/items?limit=1", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["items"]), 1)

    def test_list_filters_by_status(self):
        Item.objects.create(title="Inbox", user=self.user)
        Item.objects.create(title="Next", status=GTDStatus.NEXT_ACTION, user=self.user)
        response = self.client.get(
            f"/api/items?status={GTDStatus.NEXT_ACTION}", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()["items"]]
        self.assertEqual(titles, ["Next"])

    def test_list_invalid_status_filter_returns_422(self):
        response = self.client.get(
            "/api/items?status=not_a_status", headers=self.headers
        )
        self.assertEqual(response.status_code, 422)

    def test_list_without_auth_returns_401(self):
        response = self.client.get("/api/items")
        self.assertEqual(response.status_code, 401)
