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
