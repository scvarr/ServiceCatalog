from django import forms

from .models import GlpiCachedLookup, InstanceType, Service


class GlpiCacheFilterForm(forms.Form):
    computer_type = forms.ChoiceField(required=False, label="Тип GLPI")
    state = forms.ChoiceField(required=False, label="Статус GLPI")
    q = forms.CharField(required=False, label="Поиск")
    show_missing = forms.BooleanField(required=False, label="Показывать отсутствующие")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["computer_type"].choices = [("", "Все типы")] + list(GlpiCachedLookup.objects.filter(kind=GlpiCachedLookup.Kind.COMPUTER_TYPE).values_list("external_id", "name"))
        self.fields["state"].choices = [("", "Все статусы")] + list(GlpiCachedLookup.objects.filter(kind=GlpiCachedLookup.Kind.STATE).values_list("external_id", "name"))


class GlpiCachedComputerImportForm(forms.Form):
    cached_computer_ids = forms.MultipleChoiceField(widget=forms.MultipleHiddenInput, required=True)
    instance_type = forms.ModelChoiceField(queryset=InstanceType.objects.filter(is_active=True), label="Локальный тип экземпляра")
    service = forms.ModelChoiceField(queryset=Service.objects.filter(is_active=True), required=False, label="Добавить в услугу")

    def __init__(self, *args, choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cached_computer_ids"].choices = [(str(value), str(value)) for value in choices]


class GlpiCacheSyncFilterForm(forms.Form):
    state = forms.ChoiceField(required=False, label="Характеристики — статус")
    computer_type = forms.ChoiceField(required=False, label="Характеристики — тип")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["state"].choices = [("", "Любой статус")] + list(GlpiCachedLookup.objects.filter(kind=GlpiCachedLookup.Kind.STATE, is_missing=False).values_list("external_id", "name"))
        self.fields["computer_type"].choices = [("", "Любой тип")] + list(GlpiCachedLookup.objects.filter(kind=GlpiCachedLookup.Kind.COMPUTER_TYPE, is_missing=False).values_list("external_id", "name"))

    def rsql_filter(self):
        if not self.is_valid():
            return ""
        rules = []
        if self.cleaned_data["state"]:
            rules.append(f"status.id=={self.cleaned_data['state']}")
        if self.cleaned_data["computer_type"]:
            rules.append(f"type.id=={self.cleaned_data['computer_type']}")
        return ";".join(rules)
