from django.http import HttpResponse
from django.views import View

from core.context_processors import THEME_COOKIE_NAME

THEME_COOKIE_MAX_AGE = 365 * 24 * 3600


class SetThemeView(View):
    """Persist the theme override cookie ("light"/"dark"; "system" clears it
    so color-scheme follows the OS again). No login required: the toggle is
    also shown on the login page."""

    def post(self, request):
        value = request.POST.get("theme", "")
        if value not in ("light", "dark", "system"):
            return HttpResponse(status=400)
        response = HttpResponse(status=204)
        if value == "system":
            response.delete_cookie(THEME_COOKIE_NAME, samesite="Lax")
        else:
            response.set_cookie(
                THEME_COOKIE_NAME,
                value,
                max_age=THEME_COOKIE_MAX_AGE,
                samesite="Lax",
            )
        return response
