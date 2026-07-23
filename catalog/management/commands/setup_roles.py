from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the standard Service Catalog groups and permissions."

    def handle(self, *args, **options):
        catalog_models = {"instancetype", "instance", "service", "servicemembership", "unitofmeasure", "servicemetriccategory", "actualservicemetric", "serverprofile", "glpiimportsession", "glpiimportpayload", "glpiimportcandidate"}
        contract_models = {"contract", "contractserviceterm", "namedcontractposition", "contractlistimport", "contractactualsnapshot", "contractactualsnapshotservice", "contractactualsnapshotinstance"}
        specifications = {
            "Readers": (catalog_models | contract_models, {"view"}),
            "Editors": (catalog_models, {"view", "add", "change"}),
            "ContractEditors": (catalog_models | contract_models, {"view", "add", "change"}),
            "Administrators": (catalog_models | contract_models, {"view", "add", "change", "delete"}),
        }
        for group_name, (models, actions) in specifications.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            permissions = Permission.objects.filter(content_type__app_label__in=["catalog", "contracts"], content_type__model__in=models, codename__regex=r"^(view|add|change|delete)_")
            group.permissions.set([p for p in permissions if p.codename.split("_", 1)[0] in actions])
            self.stdout.write(f"{group_name}: {group.permissions.count()} permissions")
