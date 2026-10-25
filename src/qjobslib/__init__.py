import datetime
import json
import logging
import os
import tempfile
from enum import Enum, auto
from pathlib import Path
from dataclasses import dataclass
from typing import Any

BASE_PATH = Path.home() / '.qjobs'

class JobSlug:
    def __init__(self, service: str, instance: str):
        self._service = service
        self._instance = instance

    @property
    def service(self) -> str:
        return self._service

    @property
    def instance(self) -> str:
        return self._instance

    @property
    def job_path(self) -> Path:
        return BASE_PATH / self.service / self.instance

    @property
    def log_path(self) -> Path:
        return self.job_path.with_suffix(".log")

    @property
    def reports_path(self) -> Path:
        return self.job_path.with_suffix(".reports")

    def get_reports(self) -> list[JobReport]:
        return JobReport.load_reports(self)

    def get_last_report(self) -> JobReport | None:
        return JobReport.load_last_report(self)


class Job(JobSlug):
    def __init__(self, service: str, instance: str):
        if service == "logs":
            raise AttributeError("Service cannot be named \"logs\"")
        super().__init__(service, instance)

        logging.getLogger().addHandler(logging.FileHandler(self.log_path))

        self._last_report = self.get_last_report()

    def submit_report(self, state: JobState, percentage: float, msg: str | None = None):
        self._last_report = JobReport(datetime.datetime.now(), self, state, percentage, msg)
        self._last_report.save()

    def submit_progress(self, percentage: float, msg: str | None = None):
        self.submit_report(self._last_report.state if self._last_report is not None else JobState.Active, percentage, msg)

    def submit_state(self, state: JobState, msg: str | None = None):
        self.submit_report(state, self._last_report.percentage if self._last_report is not None else 0, msg)


class JobState(Enum):
    Inactive = auto()
    Active = auto()
    ActiveWaiting = auto()
    Completed = auto()
    Failed = auto()


@dataclass(frozen=True)
class JobReport:
    timestamp: datetime.datetime
    job: JobSlug
    state: JobState
    percentage: float
    state_msg: str | None

    def save(self):
        report = {
            "timestamp": self.timestamp.isoformat(),
            "service": self.job.service,
            "instance": self.job.instance,
            "state": self.state,
            "percentage": self.percentage,
            "state_msg": self.state_msg,
        }

        if self.job.reports_path.exists():
            with open(self.job.reports_path, "r") as file:
                reports = json.load(file)
            reports["history"].insert(0, reports["current"])
            reports["current"] = report
        else:
            reports = {"current": report, "history": []}

        if self.job.reports_path.exists():
            directory = self.job.reports_path.parent
            directory.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as file:
                json.dump(reports, file)
                file.flush()
                os.fsync(file.fileno())
                temp_name = file.name

            try:
                os.replace(temp_name, self.job.reports_path)
            except:
                if os.path.exists(temp_name):
                    try:
                        os.unlink(temp_name)
                    except:
                        pass


        else:
            with open(self.job.reports_path, "w") as file:
                json.dump(reports, file)

    @classmethod
    def deserialize(cls, report: dict[str, Any]) -> JobReport:
        timestamp = datetime.datetime.fromisoformat(report["timestamp"])
        job = JobSlug(report["service"], report["instance"])
        state = JobState(report["state"])
        percentage = report["percentage"]
        state_msg = report["state_msg"]
        return JobReport(timestamp, job, state, percentage, state_msg)

    @classmethod
    def load_reports(cls, slug: JobSlug) -> list[JobReport]:
        if not slug.job_path.exists():
            return []
        with open(slug.reports_path, "r") as file:
            reports = json.load(file)

        if not "history" in reports or not "current" in reports:
            return []

        all_reports = reports["history"]
        all_reports.insert(0, reports["current"])

        return list(map(cls.deserialize, all_reports))

    @classmethod
    def load_last_report(cls, slug: JobSlug) -> JobReport | None:
        if not slug.job_path.exists():
            return None
        with open(slug.job_path, "r") as file:
            reports = json.load(file)
            if "current" in reports:
                return JobReport.deserialize(reports["current"])
            return None
