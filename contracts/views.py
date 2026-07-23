from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from .models import Contract, ContractServiceTerm
from .services import comparison_for_term, import_csv


@login_required
def contract_list(request):
    return render(request, "contracts/contract_list.html", {"contracts": Contract.objects.prefetch_related("service_terms")})


@login_required
def contract_detail(request, pk):
    contract = get_object_or_404(Contract.objects.prefetch_related("service_terms__service"), pk=pk)
    return render(request, "contracts/contract_detail.html", {"contract": contract})


@login_required
def term_comparison(request, pk):
    term = get_object_or_404(ContractServiceTerm.objects.select_related("contract", "service"), pk=pk)
    return render(request, "contracts/term_comparison.html", {"term": term, "comparison": comparison_for_term(term)})


@permission_required("contracts.add_contractlistimport", raise_exception=True)
def import_list(request, pk):
    term = get_object_or_404(ContractServiceTerm, pk=pk)
    if request.method == "POST":
        upload = request.FILES.get("csv_file")
        if not upload:
            messages.error(request, "Выберите CSV-файл.")
        else:
            try:
                import_csv(term, upload.read().decode("utf-8-sig"), upload.name, request.user)
                messages.success(request, "Перечень импортирован.")
                return redirect("contracts:term_comparison", pk=term.pk)
            except (UnicodeDecodeError, ValueError) as exc:
                messages.error(request, str(exc))
    return render(request, "contracts/import_list.html", {"term": term})

