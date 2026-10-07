from __future__ import annotations

from pydantic import EmailStr, Field, HttpUrl

from vsa_commerce.domain.models.base import Model, NonEmptyStr, Slug, Timezone


class Business(Model):
    id: Slug
    name: NonEmptyStr
    brand_names: list[NonEmptyStr] = Field(min_length=1, description="Every name customers use for the business.")
    description: NonEmptyStr
    website: HttpUrl
    contact_email: EmailStr | None = None
    timezone: Timezone
    links: dict[str, HttpUrl] = Field(default_factory=dict)
