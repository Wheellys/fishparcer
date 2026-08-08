from urllib.parse import urlencode

from django import forms
from django.core.exceptions import ValidationError

from fishparcer.catches.models import CatchRecord


class FetchUrlForm(forms.Form):
    url = forms.URLField(
        label="Ссылка API",
        required=False,
        widget=forms.URLInput(
            attrs={
                "class": "form-control",
                "placeholder": "https://example.com/api/...",
            },
        ),
    )
    json_body = forms.CharField(
        label="Или вставьте JSON из Postman",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control font-monospace",
                "rows": 10,
                "placeholder": '[{"id": "c-123", "fishType": "Окунь", ...}]',
            },
        ),
        help_text="Postman → Body → Copy response. Работает всегда, даже если URL недоступен.",
    )
    session_cookie = forms.CharField(
        label="Cookie сессии",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Значение заголовка Cookie из Postman",
            },
        ),
        help_text="Postman → Headers → Cookie (если API требует авторизацию)",
    )
    auth_token = forms.CharField(
        label="Токен авторизации",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Bearer токен из Postman → Authorization",
            },
        ),
    )
    extra_headers = forms.CharField(
        label="Дополнительные заголовки",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control font-monospace",
                "rows": 3,
                "placeholder": "Cookie: session=...\nX-Api-Key: ...",
            },
        ),
        help_text="По одному на строку: Key: Value",
    )
    download_photos = forms.BooleanField(
        label="Скачать фото на сервер",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    source_name = forms.CharField(
        label="Название источника",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Необязательно",
            },
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        url = cleaned_data.get("url")
        json_body = (cleaned_data.get("json_body") or "").strip()
        if not url and not json_body:
            raise ValidationError("Укажите ссылку из Postman или вставьте JSON-ответ.")
        cleaned_data["json_body"] = json_body
        return cleaned_data


class CatchRecordForm(forms.ModelForm):
    is_confirmed = forms.BooleanField(
        label="Подтверждён",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = CatchRecord
        fields = [
            "fish_type",
            "reservoir_name",
            "region",
            "country",
            "weight",
            "caught",
            "bites",
            "fishing_style",
            "fishing_date",
            "time_start",
            "time_end",
            "bite_status",
            "quote",
        ]
        widgets = {
            "fish_type": forms.TextInput(attrs={"class": "form-control"}),
            "reservoir_name": forms.TextInput(attrs={"class": "form-control"}),
            "region": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
            "weight": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "caught": forms.NumberInput(attrs={"class": "form-control"}),
            "bites": forms.NumberInput(attrs={"class": "form-control"}),
            "fishing_style": forms.TextInput(attrs={"class": "form-control"}),
            "fishing_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "time_start": forms.TextInput(attrs={"class": "form-control"}),
            "time_end": forms.TextInput(attrs={"class": "form-control"}),
            "bite_status": forms.TextInput(attrs={"class": "form-control"}),
            "quote": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["is_confirmed"].initial = (
                self.instance.review_status == CatchRecord.ReviewStatus.CONFIRMED
            )


class CatchFilterForm(forms.Form):
    CONFIRMED_ALL = ""
    CONFIRMED_YES = "yes"
    CONFIRMED_NO = "no"

    PHOTO_ALL = ""
    PHOTO_WITH = "with"
    PHOTO_WITHOUT = "without"

    q = forms.CharField(
        label="Поиск",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Рыба, водоём, регион..."},
        ),
    )
    fish = forms.MultipleChoiceField(
        label="Рыба",
        required=False,
        choices=[],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    is_confirmed = forms.ChoiceField(
        label="Подтверждён",
        required=False,
        choices=[
            (CONFIRMED_ALL, "Все"),
            (CONFIRMED_YES, "Да"),
            (CONFIRMED_NO, "Нет"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    region = forms.MultipleChoiceField(
        label="Region",
        required=False,
        choices=[],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    has_photo = forms.ChoiceField(
        label="Фото",
        required=False,
        choices=[
            (PHOTO_ALL, "Все"),
            (PHOTO_WITH, "С фото"),
            (PHOTO_WITHOUT, "Без фото"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, fish_options=None, region_options=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fish_options = [name for name in (fish_options or []) if name]
        self.region_options = [name for name in (region_options or []) if name]
        self.fields["fish"].choices = [
            (str(index), name) for index, name in enumerate(self.fish_options, start=1)
        ]
        self.fields["region"].choices = [
            (str(index), name) for index, name in enumerate(self.region_options, start=1)
        ]

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data["fish"] = self._normalize_all_selected(
            cleaned_data.get("fish") or [],
            len(self.fish_options),
        )
        cleaned_data["region"] = self._normalize_all_selected(
            cleaned_data.get("region") or [],
            len(self.region_options),
        )
        return cleaned_data

    @staticmethod
    def _normalize_all_selected(selected, total_count):
        if not selected or total_count == 0:
            return []
        all_ids = {str(index) for index in range(1, total_count + 1)}
        if set(selected) == all_ids:
            return []
        return selected

    def resolve_fish_names(self):
        if not self.is_valid():
            return []
        return [self.fish_options[int(fish_id) - 1] for fish_id in self.cleaned_data.get("fish") or []]

    def resolve_region_names(self):
        if not self.is_valid():
            return []
        return [
            self.region_options[int(region_id) - 1]
            for region_id in self.cleaned_data.get("region") or []
        ]

    def get_query_params(self):
        if not self.is_valid():
            return []

        params = []
        query = self.cleaned_data.get("q")
        if query:
            params.append(("q", query))

        for fish_id in self.cleaned_data.get("fish") or []:
            params.append(("fish", fish_id))

        for region_id in self.cleaned_data.get("region") or []:
            params.append(("region", region_id))

        is_confirmed = self.cleaned_data.get("is_confirmed")
        if is_confirmed:
            params.append(("is_confirmed", is_confirmed))

        has_photo = self.cleaned_data.get("has_photo")
        if has_photo:
            params.append(("has_photo", has_photo))

        return params

    def get_query_string(self):
        return urlencode(self.get_query_params(), doseq=True)
