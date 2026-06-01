from __future__ import annotations

from copy import deepcopy

from flask import abort
from sqlalchemy import and_
from sqlalchemy import or_

from app.logging import get_logger
from app.models import InventoryView
from app.models import db
from app.models.views import MAX_VIEW_NAME_LENGTH
from lib.db import session_guard

logger = get_logger(__name__)

CLONE_NAME_PREFIX = "Copy of "


def _visibility_filter(org_id: str, username: str):
    """Return a SQLAlchemy filter for views visible to the given user.

    Visible views are:
    - System views (org_id IS NULL)
    - Org-wide views in the same org
    - Private views created by the user in the same org
    """
    return or_(
        InventoryView.org_id.is_(None),
        and_(
            InventoryView.org_id == org_id,
            or_(
                InventoryView.created_by == username,
                InventoryView.org_wide.is_(True),
            ),
        ),
    )


def get_views_list(org_id: str, username: str, page: int = 1, per_page: int = 50) -> dict:
    query = InventoryView.query.filter(_visibility_filter(org_id, username)).order_by(InventoryView.modified_on.desc())

    total = query.count()
    views = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "count": len(views),
        "page": page,
        "per_page": per_page,
        "results": [_serialize_view(v, username) for v in views],
    }


def get_view_by_id(view_id: str, org_id: str, username: str) -> dict:
    view = InventoryView.query.filter(
        InventoryView.id == view_id,
        _visibility_filter(org_id, username),
    ).one_or_none()

    if view is None:
        abort(404, "View not found.")

    return _serialize_view(view, username)


def create_view(data: dict, org_id: str, username: str) -> dict:
    view = InventoryView(
        org_id=org_id,
        name=data["name"],
        description=data.get("description"),
        configuration=data["configuration"],
        org_wide=data.get("org_wide", False),
        created_by=username,
    )

    with session_guard(db.session, close=False):
        db.session.add(view)

    db.session.refresh(view)
    return _serialize_view(view, username)


def update_view(view_id: str, data: dict, org_id: str, username: str) -> dict:
    view = InventoryView.query.filter(
        InventoryView.id == view_id,
        _visibility_filter(org_id, username),
    ).one_or_none()

    if view is None:
        abort(404, "View not found.")

    if view.org_id is None:
        abort(403, "System views cannot be modified.")

    if view.created_by != username:
        abort(403, "Only the view creator can update this view.")

    with session_guard(db.session, close=False):
        view.patch(data)

    db.session.refresh(view)
    return _serialize_view(view, username)


def delete_view(view_id: str, org_id: str, username: str) -> None:
    view = InventoryView.query.filter(
        InventoryView.id == view_id,
        _visibility_filter(org_id, username),
    ).one_or_none()

    if view is None:
        abort(404, "View not found.")

    if view.org_id is None:
        abort(403, "System views cannot be deleted.")

    if view.created_by != username:
        abort(403, "Only the view creator can delete this view.")

    with session_guard(db.session):
        db.session.delete(view)


def clone_view(view_id: str, org_id: str, username: str) -> dict:
    source = InventoryView.query.filter(
        InventoryView.id == view_id,
        _visibility_filter(org_id, username),
    ).one_or_none()

    if source is None:
        abort(404, "Source view not found.")

    clone_name = f"{CLONE_NAME_PREFIX}{source.name}"[:MAX_VIEW_NAME_LENGTH]

    cloned = InventoryView(
        org_id=org_id,
        name=clone_name,
        description=source.description,
        configuration=deepcopy(source.configuration),
        org_wide=False,
        created_by=username,
    )

    with session_guard(db.session, close=False):
        db.session.add(cloned)

    db.session.refresh(cloned)
    return _serialize_view(cloned, username)


def _serialize_view(view: InventoryView, username: str) -> dict:
    return {
        "id": str(view.id),
        "org_id": view.org_id,
        "name": view.name,
        "description": view.description,
        "is_system_view": view.org_id is None,
        "configuration": view.configuration,
        "org_wide": view.org_wide,
        "is_owner": view.created_by == username,
        "created_by": view.created_by,
        "created_at": view.created_on.isoformat() if view.created_on else None,
        "updated_at": view.modified_on.isoformat() if view.modified_on else None,
    }
