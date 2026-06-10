from dataclasses import dataclass, field
from typing import List
from enum import Enum
import time


class JobStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    DONE       = "done"
    FAILED     = "failed"


@dataclass
class AdJob:
    job_id: str
    sender: str                  # WhatsApp number of dad
    image_paths: List[str]       # Local paths of uploaded jewellery images
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    pollen_required: float = 0.0
    error: str = ""

    def calculate_pollen(self, video_duration: float, pollen_per_second: float) -> float:
        self.pollen_required = len(self.image_paths) * video_duration * pollen_per_second
        return self.pollen_required
