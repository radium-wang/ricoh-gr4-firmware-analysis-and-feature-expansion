"""Evidence-based camera coverage. This catalog never generates camera scripts."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CameraProfile:
    id: str
    name: str
    workflow: str | None
    model: str | None
    tested_versions: tuple[str, ...]
    evidence: str


PROFILES = (
    CameraProfile('gr3', 'GR III', None, None, (), 'No model-specific replacement evidence.'),
    CameraProfile('gr3-street', 'GR III Street Edition', None, None, (), 'Dedicated resource and transfer method unverified.'),
    CameraProfile('gr3-diary', 'GR III Diary Edition', None, None, (), 'Dedicated resource and transfer method unverified.'),
    CameraProfile('gr3-hdf', 'GR III HDF', None, None, (), 'Resource, transfer method and JPEG profile unverified.'),
    CameraProfile('gr3x', 'GR IIIx', None, None, (), 'Urban evidence does not establish standard-body compatibility.'),
    CameraProfile('gr3x-urban', 'GR IIIx Urban Edition', 'URBAN', 'URBAN', ('1.60',), 'Replacement and restoration observed on one body; complete app pending camera tests.'),
    CameraProfile('gr3x-hdf', 'GR IIIx HDF', None, None, (), 'Urban evidence does not establish HDF compatibility.'),
    CameraProfile('gr4', 'GR IV', 'FAMILY', 'STANDARD', ('1.11',), 'Model/target and copy evidence; complete app pending camera tests.'),
    CameraProfile('gr4-hdf', 'GR IV HDF', 'FAMILY', 'HDF', ('1.11',), 'Model/target and separate image trials; complete app pending camera tests.'),
    CameraProfile('gr4-mono', 'GR IV Monochrome', 'FAMILY', 'MONO', (), 'Model and target observed, but firmware version was not recorded.'),
)


def profile_for(workflow, model):
    return next((p for p in PROFILES if p.workflow == workflow and p.model == model), None)


def installation_allowed(workflow, model, firmware):
    profile = profile_for(workflow, model)
    return bool(profile and firmware in profile.tested_versions)
