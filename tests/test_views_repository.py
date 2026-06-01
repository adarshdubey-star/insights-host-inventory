import uuid

import pytest
from werkzeug.exceptions import Forbidden
from werkzeug.exceptions import NotFound

from app.models import InventoryView
from app.models import db
from lib.views_repository import CLONE_NAME_PREFIX
from lib.views_repository import clone_view
from lib.views_repository import create_view
from lib.views_repository import delete_view
from lib.views_repository import get_view_by_id
from lib.views_repository import get_views_list
from lib.views_repository import update_view

ORG_ID = "test-org-1"
OTHER_ORG = "test-org-2"
USERNAME = "testuser"
OTHER_USER = "otheruser"

VALID_CONFIG = {"columns": [{"key": "display_name", "visible": True}]}


def _create_db_view(
    name="Test View",
    org_id=ORG_ID,
    created_by=USERNAME,
    configuration=None,
    org_wide=False,
):
    view = InventoryView(
        org_id=org_id,
        name=name,
        configuration=configuration or VALID_CONFIG,
        org_wide=org_wide,
        created_by=created_by,
    )
    db.session.add(view)
    db.session.commit()
    return view


def _create_system_view(name="Red Hat Default", configuration=None):
    view = InventoryView(
        org_id=None,
        name=name,
        configuration=configuration or VALID_CONFIG,
        org_wide=True,
        created_by=None,
    )
    db.session.add(view)
    db.session.commit()
    return view


class TestGetViewsList:
    def test_returns_own_private_views(self, flask_app):  # noqa: ARG002
        _create_db_view(name="My Private View", org_wide=False)

        result = get_views_list(ORG_ID, USERNAME)

        assert result["total"] == 1
        assert result["results"][0]["name"] == "My Private View"

    def test_returns_org_wide_views(self, flask_app):  # noqa: ARG002
        _create_db_view(name="Shared View", created_by=OTHER_USER, org_wide=True)

        result = get_views_list(ORG_ID, USERNAME)

        assert result["total"] == 1
        assert result["results"][0]["name"] == "Shared View"

    def test_returns_system_views(self, flask_app):  # noqa: ARG002
        _create_system_view(name="System Default")

        result = get_views_list(ORG_ID, USERNAME)

        assert result["total"] == 1
        assert result["results"][0]["name"] == "System Default"
        assert result["results"][0]["is_system_view"] is True

    def test_excludes_other_users_private_views(self, flask_app):  # noqa: ARG002
        _create_db_view(name="Other Private", created_by=OTHER_USER, org_wide=False)

        result = get_views_list(ORG_ID, USERNAME)

        assert result["total"] == 0

    def test_excludes_other_org_views(self, flask_app):  # noqa: ARG002
        _create_db_view(name="Other Org View", org_id=OTHER_ORG, created_by=OTHER_USER, org_wide=True)

        result = get_views_list(ORG_ID, USERNAME)

        assert result["total"] == 0

    def test_pagination(self, flask_app):  # noqa: ARG002
        for i in range(5):
            _create_db_view(name=f"View {i}")

        result = get_views_list(ORG_ID, USERNAME, page=1, per_page=2)

        assert result["total"] == 5
        assert result["count"] == 2
        assert result["page"] == 1
        assert result["per_page"] == 2

    def test_ordered_by_modified_on_desc(self, flask_app):  # noqa: ARG002
        v1 = _create_db_view(name="Old View")
        v2 = _create_db_view(name="New View")

        result = get_views_list(ORG_ID, USERNAME)

        assert result["results"][0]["id"] == str(v2.id)
        assert result["results"][1]["id"] == str(v1.id)

    def test_is_owner_flag(self, flask_app):  # noqa: ARG002
        _create_db_view(name="Mine", created_by=USERNAME, org_wide=True)
        _create_db_view(name="Theirs", created_by=OTHER_USER, org_wide=True)

        result = get_views_list(ORG_ID, USERNAME)

        by_name = {r["name"]: r for r in result["results"]}
        assert by_name["Mine"]["is_owner"] is True
        assert by_name["Theirs"]["is_owner"] is False


class TestGetViewById:
    def test_returns_visible_view(self, flask_app):  # noqa: ARG002
        view = _create_db_view(name="My View")

        result = get_view_by_id(str(view.id), ORG_ID, USERNAME)

        assert result["name"] == "My View"
        assert result["id"] == str(view.id)

    def test_returns_system_view(self, flask_app):  # noqa: ARG002
        view = _create_system_view()

        result = get_view_by_id(str(view.id), ORG_ID, USERNAME)

        assert result["is_system_view"] is True

    def test_404_for_nonexistent_view(self, flask_app):  # noqa: ARG002
        with pytest.raises(NotFound):
            get_view_by_id(str(uuid.uuid4()), ORG_ID, USERNAME)

    def test_404_for_other_users_private_view(self, flask_app):  # noqa: ARG002
        view = _create_db_view(created_by=OTHER_USER, org_wide=False)

        with pytest.raises(NotFound):
            get_view_by_id(str(view.id), ORG_ID, USERNAME)


class TestCreateView:
    def test_creates_view(self, flask_app):  # noqa: ARG002
        data = {"name": "New View", "configuration": VALID_CONFIG}

        result = create_view(data, ORG_ID, USERNAME)

        assert result["name"] == "New View"
        assert result["org_id"] == ORG_ID
        assert result["created_by"] == USERNAME
        assert result["is_owner"] is True
        assert result["org_wide"] is False

    def test_creates_org_wide_view(self, flask_app):  # noqa: ARG002
        data = {"name": "Shared", "configuration": VALID_CONFIG, "org_wide": True}

        result = create_view(data, ORG_ID, USERNAME)

        assert result["org_wide"] is True

    def test_ignores_client_provided_identity_fields(self, flask_app):  # noqa: ARG002
        data = {
            "name": "Sneaky",
            "configuration": VALID_CONFIG,
            "org_id": OTHER_ORG,
            "created_by": OTHER_USER,
        }

        result = create_view(data, ORG_ID, USERNAME)

        assert result["org_id"] == ORG_ID
        assert result["created_by"] == USERNAME

    def test_creates_view_with_description(self, flask_app):  # noqa: ARG002
        data = {"name": "Described", "configuration": VALID_CONFIG, "description": "A test view"}

        result = create_view(data, ORG_ID, USERNAME)

        assert result["description"] == "A test view"


class TestUpdateView:
    def test_updates_name(self, flask_app):  # noqa: ARG002
        view = _create_db_view(name="Old Name")

        result = update_view(str(view.id), {"name": "New Name"}, ORG_ID, USERNAME)

        assert result["name"] == "New Name"

    def test_updates_multiple_fields(self, flask_app):  # noqa: ARG002
        view = _create_db_view()

        result = update_view(
            str(view.id),
            {"name": "Updated", "description": "New desc", "org_wide": True},
            ORG_ID,
            USERNAME,
        )

        assert result["name"] == "Updated"
        assert result["description"] == "New desc"
        assert result["org_wide"] is True

    def test_403_for_system_view(self, flask_app):  # noqa: ARG002
        view = _create_system_view()

        with pytest.raises(Forbidden):
            update_view(str(view.id), {"name": "Hacked"}, ORG_ID, USERNAME)

    def test_403_for_non_owner(self, flask_app):  # noqa: ARG002
        view = _create_db_view(created_by=OTHER_USER, org_wide=True)

        with pytest.raises(Forbidden):
            update_view(str(view.id), {"name": "Hacked"}, ORG_ID, USERNAME)

    def test_404_for_nonexistent_view(self, flask_app):  # noqa: ARG002
        with pytest.raises(NotFound):
            update_view(str(uuid.uuid4()), {"name": "X"}, ORG_ID, USERNAME)


class TestDeleteView:
    def test_deletes_own_view(self, flask_app):  # noqa: ARG002
        view = _create_db_view()

        delete_view(str(view.id), ORG_ID, USERNAME)

        assert db.session.get(InventoryView, view.id) is None

    def test_403_for_system_view(self, flask_app):  # noqa: ARG002
        view = _create_system_view()

        with pytest.raises(Forbidden):
            delete_view(str(view.id), ORG_ID, USERNAME)

    def test_403_for_non_owner(self, flask_app):  # noqa: ARG002
        view = _create_db_view(created_by=OTHER_USER, org_wide=True)

        with pytest.raises(Forbidden):
            delete_view(str(view.id), ORG_ID, USERNAME)

    def test_404_for_nonexistent_view(self, flask_app):  # noqa: ARG002
        with pytest.raises(NotFound):
            delete_view(str(uuid.uuid4()), ORG_ID, USERNAME)

    def test_404_for_view_from_other_org(self, flask_app):  # noqa: ARG002
        view = _create_db_view(org_id=OTHER_ORG, created_by=OTHER_USER)

        with pytest.raises(NotFound):
            delete_view(str(view.id), ORG_ID, USERNAME)


class TestCloneView:
    def test_clones_view(self, flask_app):  # noqa: ARG002
        original = _create_db_view(name="Original", created_by=OTHER_USER, org_wide=True)

        result = clone_view(str(original.id), ORG_ID, USERNAME)

        assert result["name"] == f"{CLONE_NAME_PREFIX}Original"
        assert result["created_by"] == USERNAME
        assert result["org_wide"] is False
        assert result["is_owner"] is True
        assert result["configuration"] == VALID_CONFIG
        assert result["id"] != str(original.id)

    def test_clones_system_view(self, flask_app):  # noqa: ARG002
        system = _create_system_view(name="System View")

        result = clone_view(str(system.id), ORG_ID, USERNAME)

        assert result["name"] == f"{CLONE_NAME_PREFIX}System View"
        assert result["org_id"] == ORG_ID
        assert result["is_system_view"] is False

    def test_clone_truncates_long_name(self, flask_app):  # noqa: ARG002
        from app.models.views import MAX_VIEW_NAME_LENGTH

        long_name = "A" * MAX_VIEW_NAME_LENGTH
        original = _create_db_view(name=long_name)

        result = clone_view(str(original.id), ORG_ID, USERNAME)

        assert len(result["name"]) == MAX_VIEW_NAME_LENGTH
        assert result["name"].startswith(CLONE_NAME_PREFIX)

    def test_clone_deep_copies_configuration(self, flask_app):  # noqa: ARG002
        config = {"columns": [{"key": "id", "visible": True}], "filters": {"os": "RHEL"}}
        original = _create_db_view(configuration=config)

        result = clone_view(str(original.id), ORG_ID, USERNAME)

        assert result["configuration"] == config
        assert result["configuration"] is not config

    def test_404_for_nonexistent_source(self, flask_app):  # noqa: ARG002
        with pytest.raises(NotFound):
            clone_view(str(uuid.uuid4()), ORG_ID, USERNAME)
