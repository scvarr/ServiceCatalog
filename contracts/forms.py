from django import forms

from .models import Contract


class ContractProjectForm(forms.ModelForm):
    fill_from_actual = forms.BooleanField(label="Заполнить из актуального состояния", required=False, initial=True)

    class Meta:
        model = Contract
        fields = ("number", "name", "period_label", "start_date", "end_date", "notes", "document_url")

    def clean(self):
        cleaned = super().clean()
        if Contract.objects.filter(status=Contract.Status.DRAFT).exists():
            raise forms.ValidationError("В системе уже есть черновик договора.")
        return cleaned
