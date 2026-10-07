from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from vsa_commerce.domain.models.base import Model
from vsa_commerce.domain.models.business import Business
from vsa_commerce.domain.models.offering import Offering


class Catalog(Model):
    business: Business
    offerings: list[Offering] = Field(min_length=1)

    @model_validator(mode="after")
    def _referential_integrity(self) -> Self:
        ids = [o.id for o in self.offerings]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate offering ids")
        known = set(ids)
        for offering in self.offerings:
            if offering.business_id != self.business.id:
                raise ValueError(
                    f"offering {offering.id!r} belongs to {offering.business_id!r}, not {self.business.id!r}"
                )
            for rel in offering.related:
                if rel.offering_id == offering.id:
                    raise ValueError(f"offering {offering.id!r} cannot relate to itself")
                if rel.offering_id not in known:
                    raise ValueError(f"offering {offering.id!r} relates to unknown offering {rel.offering_id!r}")
        return self

    def get(self, offering_id: str) -> Offering:
        for offering in self.offerings:
            if offering.id == offering_id:
                return offering
        raise KeyError(offering_id)
