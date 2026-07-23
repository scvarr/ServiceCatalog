import csv
import hashlib
import io
from collections import Counter
from django.db import transaction
from catalog.models import Instance
from .models import ContractListImport, NamedContractPosition


def comparison_for_term(term):
    """Return calculated comparison values; no comparison state is persisted."""
    active_ids = set(term.service.memberships.filter(status="active").values_list("instance_id", flat=True))
    positions = term.named_positions.exclude(match_status=NamedContractPosition.MatchStatus.IGNORED)
    matched_ids = set(positions.filter(match_status=NamedContractPosition.MatchStatus.MATCHED).values_list("instance_id", flat=True))
    return {
        "matched": positions.filter(match_status="matched", instance_id__in=active_ids),
        "contract_only": positions.filter(match_status="matched").exclude(instance_id__in=active_ids),
        "actual_only": Instance.objects.filter(pk__in=active_ids - matched_ids),
        "unmatched": positions.filter(match_status="unmatched"),
        "ambiguous": positions.filter(match_status="ambiguous"),
        "actual_count": len(active_ids),
        "upper_limit": term.allowed_upper_limit,
    }


@transaction.atomic
def import_csv(term, csv_text, filename, user=None):
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or "catalog_code" not in reader.fieldnames:
        raise ValueError("CSV должен содержать заголовок catalog_code.")
    batch = ContractListImport.objects.create(
        term=term, original_filename=filename, file_hash=hashlib.sha256(csv_text.encode("utf-8")).hexdigest(), raw_csv=csv_text, created_by=user
    )
    stats = Counter()
    for row in reader:
        source_identifier = (row.get("catalog_code") or "").strip()
        matches = Instance.objects.filter(catalog_code=source_identifier)
        if not source_identifier:
            status, instance = NamedContractPosition.MatchStatus.UNMATCHED, None
        elif matches.count() == 1:
            status, instance = NamedContractPosition.MatchStatus.MATCHED, matches.first()
        elif matches.exists():
            status, instance = NamedContractPosition.MatchStatus.AMBIGUOUS, None
        else:
            status, instance = NamedContractPosition.MatchStatus.UNMATCHED, None
        NamedContractPosition.objects.create(
            term=term, source_identifier=source_identifier, source_name=(row.get("name") or "").strip(),
            source_data=row, instance=instance, match_status=status, import_batch=batch, created_by=user, updated_by=user
        )
        stats[status] += 1
    batch.total_rows = sum(stats.values())
    batch.matched_rows = stats[NamedContractPosition.MatchStatus.MATCHED]
    batch.unmatched_rows = stats[NamedContractPosition.MatchStatus.UNMATCHED]
    batch.ambiguous_rows = stats[NamedContractPosition.MatchStatus.AMBIGUOUS]
    batch.status = ContractListImport.Status.COMPLETED
    batch.save(update_fields=["total_rows", "matched_rows", "unmatched_rows", "ambiguous_rows", "status", "updated_at"])
    return batch

