"""Canonical relational models.

Importing this package registers every table on ``Base.metadata``. Application code should
import model classes from their owning modules; migration/tests may import this package to
ensure the complete schema is registered.
"""

from app.models.ai import AIClaim, AIClaimEvidence, AIUsage, PromptRun
from app.models.assessments import AssessmentFactor, OpportunityAssessment, ProductFitAssessment
from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.configuration import ConfigVersion, ScoringConfig
from app.models.contacts import ContactAssessment, ContactCandidate, VerificationEvent
from app.models.crm import CRMRecord, CRMSyncAttempt
from app.models.entities import (
    Organization,
    OrganizationAddress,
    OrganizationAlias,
    OrganizationDomain,
    Person,
    PersonAlias,
    PersonContactPoint,
)
from app.models.outcomes import CommercialOutcome
from app.models.pipeline import FieldHistory, PipelineEvent, PipelineRun
from app.models.projects import (
    Project,
    ProjectGroup,
    ProjectOrganization,
    ProjectPerson,
    ProjectRelationship,
    ProjectSignal,
)
from app.models.source import SourceDocument, SourceEvidence, SourceObservation
from app.models.trust import ExternalEvidence, QualityFlag, WorkflowException
from app.models.workflows import CommercialMotion, NextAction

__all__ = [
    "Base",
    "SourceDocument",
    "SourceObservation",
    "SourceEvidence",
    "ProjectGroup",
    "Project",
    "ProjectRelationship",
    "ProjectSignal",
    "Organization",
    "OrganizationAlias",
    "OrganizationDomain",
    "OrganizationAddress",
    "Person",
    "PersonAlias",
    "PersonContactPoint",
    "ProjectOrganization",
    "ProjectPerson",
    "ExternalEvidence",
    "QualityFlag",
    "WorkflowException",
    "OpportunityAssessment",
    "AssessmentFactor",
    "ProductFitAssessment",
    "ContactCandidate",
    "ContactAssessment",
    "VerificationEvent",
    "CommercialMotion",
    "NextAction",
    "CRMRecord",
    "CRMSyncAttempt",
    "PipelineRun",
    "PipelineEvent",
    "FieldHistory",
    "CommercialOutcome",
    "ConfigVersion",
    "ScoringConfig",
    "PromptRun",
    "AIClaim",
    "AIClaimEvidence",
    "AIUsage",
    "AuditEvent",
]
