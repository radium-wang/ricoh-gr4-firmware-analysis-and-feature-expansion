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

# Official update history is a selection aid, not installation evidence.
OFFICIAL_HISTORY = {
    'GR III': ('2.10', '2.00', '1.92', '1.91', '1.81', '1.71', '1.70', '1.61', '1.60', '1.50', '1.41', '1.31', '1.30', '1.20', '1.11', '1.10'),
    'GR IIIx': ('1.60', '1.50', '1.42', '1.41', '1.31', '1.21', '1.20', '1.11', '1.10', '1.02', '1.01'),
    'GR IV': ('1.11', '1.04', '1.03'),
}


def profile_by_id(profile_id):
    return next((p for p in PROFILES if p.id == profile_id), None)


def camera_family(profile_id):
    if not profile_by_id(profile_id):
        raise ValueError('Unknown camera profile.')
    return 'GR IV' if profile_id.startswith('gr4') else 'GR IIIx' if profile_id.startswith('gr3x') else 'GR III'


def research_versions(profile_id):
    # The IV update page excludes Monochrome; do not suggest its color-body versions.
    return () if profile_id == 'gr4-mono' else OFFICIAL_HISTORY[camera_family(profile_id)]


def profile_for(workflow, model):
    return next((p for p in PROFILES if p.workflow == workflow and p.model == model), None)


def installation_allowed(workflow, model, firmware):
    profile = profile_for(workflow, model)
    return bool(profile and firmware in profile.tested_versions)
