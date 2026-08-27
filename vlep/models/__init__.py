"""
VLEP ORM Models — Package Initializer.

Imports all model modules so SQLAlchemy metadata discovers every table.
The models are a 1:1 Python representation of the PostgreSQL schema defined
in ``Combined epipheno schema sql.sql`` (migrations 001–009).
"""

from vlep.models.base import Base  # noqa: F401
from vlep.models.core import Cohort, CohortMembership, Patient  # noqa: F401
from vlep.models.csep import (  # noqa: F401
    CSEPProfile,
    ProfileAssertionTrace,
    ProfileClaimTrace,
    ProfileEventTrace,
)
from vlep.models.evidence import LedgerEvent, LedgerEventNote  # noqa: F401
from vlep.models.governance import (  # noqa: F401
    AccessLog,
    AlertEvent,
    DataQualityRun,
    ModelDriftRun,
)
from vlep.models.ingestion import IngestionRun, RawResource, SourceSystem  # noqa: F401
from vlep.models.literature import (  # noqa: F401
    ClaimEvidenceMetadata,
    ClaimSupportingSource,
    ClaimTieringResult,
    CorpusClaim,
    CorpusRelease,
    Document,
    DocumentSection,
    HeuristicRuleset,
    PhenotypeClaim,
)
from vlep.models.modeling import (  # noqa: F401
    LatentStateSequence,
    LpaRun,
    ModelVersion,
    Prediction,
    TimeToEventHazard,
    ValidationMetricResult,
)
from vlep.models.nosology import (  # noqa: F401
    FrameworkVersion,
    ReinterpretationJob,
    ReinterpretationResult,
    ResolutionRule,
    TaxonomyEdge,
    TaxonomyTerm,
)
from vlep.models.ontology import (  # noqa: F401
    Concept,
    ConceptEdge,
    ConceptEmbedding,
    ConceptMapping,
    EmbeddingVersion,
    Vocabulary,
)
from vlep.models.phenotyping import (  # noqa: F401
    AssertionSupportClaim,
    AssertionSupportEvent,
    FeatureDefinition,
    FeatureSet,
    FeatureValue,
    FeatureWeightPrior,
    PatientTrajectorySnapshot,
    PhenotypeAssertion,
    TemporalFeatureWindow,
)
from vlep.models.review import (  # noqa: F401
    Adjudication,
    IssueReport,
    ReviewDecision,
    ReviewTask,
    SourceTextVerification,
    ValidationCohort,
    ValidationObservation,
)
