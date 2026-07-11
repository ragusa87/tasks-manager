from django.core.exceptions import ValidationError
from django.db import transaction
from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate
from ninja.responses import Status

from task_processor.api.schemas import ItemIn, ItemOut
from task_processor.constants import GTDStatus
from task_processor.models import Area, Context, Item, Tag

router = Router(tags=["items"])


def _resolve_owned(model, ids, user, label):
    """Return the user's instances for ids, or raise 422 if any id is unknown."""
    objects = list(model.objects.filter(user=user, id__in=ids))
    if len(objects) != len(set(ids)):
        raise HttpError(422, f"Unknown {label} id(s)")
    return objects


def create_item(user, payload: ItemIn) -> Item:
    """Create an Item for user from a validated payload (HTTP-free unit)."""
    data = payload.model_dump(
        exclude={"parent_id", "area_id", "context_ids", "tag_ids"}
    )
    item = Item(user=user, **data)

    if payload.parent_id is not None:
        parent = Item.objects.filter(user=user, pk=payload.parent_id).first()
        if parent is None:
            raise HttpError(422, "Unknown parent id")
        item.parent = parent

    if payload.area_id is not None:
        item.area = _resolve_owned(Area, [payload.area_id], user, "area")[0]

    contexts = _resolve_owned(Context, payload.context_ids, user, "context")
    tags = _resolve_owned(Tag, payload.tag_ids, user, "tag")

    # Enforce the same model validation as the web forms (Item.clean():
    # waiting_for_person, parent status, nesting depth, circular references)
    try:
        item.full_clean()
    except ValidationError as error:
        raise HttpError(422, "; ".join(error.messages))

    with transaction.atomic():
        item.save()
        item.contexts.set(contexts)
        item.tags.set(tags)
    return item


@router.post("", response={201: ItemOut})
def create_item_endpoint(request, payload: ItemIn):
    return Status(201, create_item(request.user, payload))


@router.get("", response=list[ItemOut])
@paginate
def list_items(request, status: GTDStatus | None = None):
    items = (
        Item.objects.for_user(request.user)
        .select_related("area")
        .prefetch_related("tags", "contexts")
    )
    if status is not None:
        items = items.filter(status=status)
    return items
