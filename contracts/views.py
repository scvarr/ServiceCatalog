from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from .forms import ContractProjectForm
from .models import Contract, ContractServiceTerm
from .services import compare_contract_to_actual, compare_contract_service_to_actual, comparison_for_term, import_csv, populate_contract_from_actual


@login_required
def contract_list(request):
    return render(request, "contracts/contract_list.html", {"contracts": Contract.objects.prefetch_related("service_terms")})


@permission_required("contracts.add_contract", raise_exception=True)
def contract_project_create(request):
    if request.method == "POST":
        form = ContractProjectForm(request.POST)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.status = Contract.Status.DRAFT
            contract.created_by = request.user
            contract.updated_by = request.user
            contract.save()
            if form.cleaned_data["fill_from_actual"]:
                populate_contract_from_actual(contract, request.user)
            messages.success(request, "Черновик договора создан.")
            return redirect("contracts:contract_detail", pk=contract.pk)
    else:
        form = ContractProjectForm()
    return render(request, "contracts/contract_project_form.html", {"form": form})


@login_required
def contract_detail(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    comparison = compare_contract_to_actual(contract)
    selected_filter = request.GET.get("comparison_filter", "all")
    filters = {
        "differences": lambda item: item["status"] not in {"match"},
        "exceeded": lambda item: item["status"] == "exceeded",
        "composition_changed": lambda item: item["composition_changed"],
        "incomplete": lambda item: item["incomplete"],
    }
    rows = comparison["services"]
    if selected_filter in filters:
        rows = [item for item in rows if filters[selected_filter](item)]
    page_obj = Paginator(rows, 25).get_page(request.GET.get("page"))
    snapshot = getattr(contract, "actual_snapshot", None)
    return render(request, "contracts/contract_detail.html", {"contract": contract, "comparison": comparison, "page_obj": page_obj, "comparison_filter": selected_filter, "snapshot": snapshot})


@login_required
def term_comparison(request, pk):
    term = get_object_or_404(ContractServiceTerm.objects.select_related("contract", "service"), pk=pk)
    return render(request, "contracts/term_comparison.html", {"term": term, "comparison": compare_contract_service_to_actual(term, include_details=True)})


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
