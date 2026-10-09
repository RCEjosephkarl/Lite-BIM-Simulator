"""Portable project input, settings and source provenance (not a DB backup)."""
from __future__ import annotations

import json
import math
from dataclasses import asdict
from typing import Literal

from pydantic import Field, field_validator, model_validator

import home_definition as homes
import materials
from framing import ModelConfig, GenerateResult
from imports.csv_plan import rows_to_elements
from imports.validators import validate_rows
from manual_inputs import MAX_MEMBERS, ManualWallFrameInput, ManualTrussInput, generate_wall, generate_truss


class Assembly(homes.Entity):
    id: str = Field(min_length=1, max_length=300)
    kind: Literal["manual_wall", "manual_truss", "csv_import", "vision_import"]
    file_name: str = ""
    uploaded_at: str = ""
    definition: dict | None = None
    legacy_members: list[dict] = Field(default_factory=list, max_length=MAX_MEMBERS)

    @model_validator(mode="after")
    def source_available(self):
        if self.definition is None and not self.legacy_members:
            raise ValueError("assembly needs a definition or explicit legacy members")
        if self.definition is not None and self.legacy_members:
            raise ValueError("assembly must have one source of geometry")
        return self


class PriceInput(homes.Entity):
    currency: Literal["USD"] = "USD"
    overrides: dict[str,float] = Field(default_factory=dict)
    saved_at: str = ""

    @field_validator("overrides")
    @classmethod
    def finite_known(cls,value):
        if any(k not in materials.MATERIALS or not math.isfinite(v) or v < 0 for k,v in value.items()):
            raise ValueError("pricing overrides need known materials and finite nonnegative USD board-metre rates")
        return value


class HomeArchive(homes.Entity):
    archive_schema_version: Literal[1] = 1
    project_revision: int | None = Field(default=None,ge=0)
    name: str = Field(default="Imported home",min_length=1,max_length=200)
    home: homes.HomeDefinition | None = None
    settings: dict = Field(default_factory=lambda:asdict(ModelConfig()))
    pricing: PriceInput = Field(default_factory=PriceInput)
    assemblies: list[Assembly] = Field(default_factory=list,max_length=1000)
    source_project: dict = Field(default_factory=dict)
    generator_version: str = ""
    catalogue_snapshot: dict = Field(default_factory=dict)

    @field_validator("settings")
    @classmethod
    def known_settings(cls,value):
        if set(value)-set(ModelConfig.__dataclass_fields__):
            raise ValueError("archive contains unknown design settings")
        json.dumps(value,allow_nan=False)
        try:
            return asdict(ModelConfig(**value).normalised())
        except (TypeError,ValueError,OverflowError):
            raise ValueError("archive design settings are invalid") from None

    @model_validator(mode="after")
    def unique_sources(self):
        # Arbitrary provenance/legacy dictionaries must still be valid JSON.
        json.dumps(self.model_dump(),allow_nan=False)
        ids=[a.id for a in self.assemblies]
        if len(ids)!=len(set(ids)):
            raise ValueError("archive assembly IDs must be unique")
        if not self.home and not self.assemblies:
            raise ValueError("archive contains no home geometry or assemblies")
        if sum(len(a.legacy_members) for a in self.assemblies)>MAX_MEMBERS:
            raise ValueError("legacy members exceed the generation budget")
        return self


def generate(archive: HomeArchive):
    """Regenerate known definitions; preserve explicitly marked legacy geometry."""
    import db
    cfg=ModelConfig(**archive.settings)
    result=homes.generate(archive.home,cfg) if archive.home else GenerateResult([],[],[])
    home_warnings=list(result.warnings)
    batch_members={}
    for assembly in archive.assemblies:
        if assembly.definition is None:
            for member in assembly.legacy_members:
                for field in ("storey","plies"):
                    value=member.get(field,1)
                    if type(value) is not int or value<1:
                        raise ValueError(f"{assembly.id}: legacy {field} must be a positive integer")
                for field,value in member.items():
                    if field in db.ELEMENT_COLUMNS and isinstance(value,(dict,list)) and field!="warnings":
                        raise ValueError(f"{assembly.id}: legacy {field} must be a scalar")
                for field in ("type_code","size","material","grade","treatment","segment_id","segment_label",
                              "truss_id","truss_label","layout_id","instance_id","member_role","start_node","end_node","note"):
                    if member.get(field) is not None and not isinstance(member[field],str):
                        raise ValueError(f"{assembly.id}: legacy {field} must be text")
                warning=member.get("warnings",[])
                if not isinstance(warning,list) or not all(isinstance(w,str) for w in warning):
                    raise ValueError(f"{assembly.id}: legacy warnings must be a list of messages")
            members=[db._decode_element(db._prepare_element(e)) for e in assembly.legacy_members]
            notes=[f"{assembly.id}: legacy geometry has no editable source definition; review and recreate"]
            for member in members:
                member["warnings"]=list(dict.fromkeys(member["warnings"]+notes))
        elif assembly.kind == "manual_wall":
            members,notes=generate_wall(ManualWallFrameInput.model_validate(assembly.definition),assembly.kind,assembly.id)
        elif assembly.kind == "manual_truss":
            members,notes=generate_truss(ManualTrussInput.model_validate(assembly.definition),assembly.kind,assembly.id)
        elif assembly.kind == "csv_import":
            validation=validate_rows(assembly.definition.get("rows",[]),assembly.definition.get("units","mm"))
            if not validation["can_preview"]:
                raise ValueError(f"{assembly.id}: saved CSV definition is invalid: {validation['errors']}")
            members,notes=rows_to_elements(validation["normalized_entities"],assembly.kind,assembly.id)
        else:
            raise ValueError("vision assemblies require explicit legacy members until a vision definition contract exists")
        for member in members:
            member.update(source=assembly.kind,source_id=assembly.id,editable=True)
        result.elements.extend(members);result.warnings.extend(notes);batch_members[assembly.id]=members
        if len(result.elements)>MAX_MEMBERS:
            raise ValueError("archive exceeds the member generation budget")
    if archive.catalogue_snapshot and archive.catalogue_snapshot != materials.catalogue_json():
        message="Imported catalogue snapshot differs from the installed catalogue; estimates use the installed catalogue and imported quote overrides"
        result.warnings.append(message);home_warnings.append(message)
    return result,batch_members,home_warnings
