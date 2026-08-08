from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from fishparcer.catches.models import PublicApiToken


class StaticApiTokenAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        token = self._get_token(request)
        if not token:
            raise AuthenticationFailed("API token required.")

        try:
            api_token = PublicApiToken.objects.get(token=token, is_active=True)
        except PublicApiToken.DoesNotExist as exc:
            raise AuthenticationFailed("Invalid or inactive API token.") from exc

        PublicApiToken.objects.filter(pk=api_token.pk).update(last_used_at=timezone.now())

        return (None, api_token)

    def _get_token(self, request) -> str:
        authorization = request.META.get("HTTP_AUTHORIZATION", "")
        if authorization.startswith(f"{self.keyword} "):
            return authorization[len(self.keyword) + 1 :].strip()

        api_token = request.META.get("HTTP_X_API_TOKEN", "").strip()
        if api_token:
            return api_token

        return ""
