from django.db import IntegrityError, transaction
from ninja import Router
from ninja.responses import Status

from task_processor.api.schemas import AreaOut, ContextOut, NamedIn, TagIn, TagOut
from task_processor.models import Area, Context, Tag

router = Router(tags=["taxonomies"])


def _get_or_create_by_name(model, user, name, **defaults):
    """Case-insensitive get-or-create, matching the web forms' iexact dedupe."""
    existing = model.objects.filter(user=user, name__iexact=name).first()
    if existing:
        return existing, False
    try:
        # atomic() keeps a fired constraint from breaking an enclosing
        # transaction, so the re-fetch below stays valid.
        with transaction.atomic():
            return model.objects.create(user=user, name=name, **defaults), True
    except IntegrityError:
        # Lost a race with a concurrent create of the same name: the
        # (name, user) unique constraint fired, so the row exists now.
        return model.objects.filter(user=user, name__iexact=name).first(), False


@router.get("/tags", response=list[TagOut])
def list_tags(request):
    return Tag.objects.filter(user=request.user)


@router.post("/tags", response={200: TagOut, 201: TagOut})
def create_tag(request, payload: TagIn):
    """Create a tag, or return the existing one matching the name
    case-insensitively (200 instead of 201)."""
    tag, created = _get_or_create_by_name(Tag, request.user, payload.name)
    return Status(201 if created else 200, tag)


@router.get("/contexts", response=list[ContextOut])
def list_contexts(request):
    return Context.objects.filter(user=request.user)


@router.post("/contexts", response={200: ContextOut, 201: ContextOut})
def create_context(request, payload: NamedIn):
    """Create a context, or return the existing one matching the name
    case-insensitively (200 instead of 201). An existing context is
    returned unchanged: the submitted description is ignored."""
    context, created = _get_or_create_by_name(
        Context, request.user, payload.name, description=payload.description
    )
    return Status(201 if created else 200, context)


@router.get("/areas", response=list[AreaOut])
def list_areas(request):
    return Area.objects.filter(user=request.user)


@router.post("/areas", response={200: AreaOut, 201: AreaOut})
def create_area(request, payload: NamedIn):
    """Create an area, or return the existing one matching the name
    case-insensitively (200 instead of 201). An existing area is
    returned unchanged: the submitted description is ignored."""
    area, created = _get_or_create_by_name(
        Area, request.user, payload.name, description=payload.description
    )
    return Status(201 if created else 200, area)
