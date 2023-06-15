# pylint: disable=missing-function-docstring,missing-class-docstring
from typing import Dict, Union
from unittest import mock

import general_superstaq as gss
import pytest
import qiskit

import qiskit_superstaq as qss


def mock_response(status_str: str) -> Dict[str, Union[str, int, Dict[str, int]]]:
    return {"status": status_str, "samples": {"10": 100}, "shots": 100}


@pytest.fixture
def backend() -> qss.SuperstaQBackend:
    provider = qss.SuperstaQProvider(api_key="token")
    return provider.get_backend("ss_example_qpu")


def test_wait_for_results(backend: qss.SuperstaQBackend) -> None:
    job = qss.SuperstaQJob(backend=backend, job_id="123abc")
    jobs = qss.SuperstaQJob(backend=backend, job_id="123abc,456def")

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Done"),
    ):
        assert job._wait_for_results(timeout=backend._provider._client.max_retry_seconds) == [
            mock_response("Done")
        ]
        assert jobs._wait_for_results(timeout=backend._provider._client.max_retry_seconds) == [
            mock_response("Done"),
            mock_response("Done"),
        ]


def test_timeout(backend: qss.SuperstaQBackend) -> None:
    job = qss.SuperstaQJob(backend=backend, job_id="123abc")

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        side_effect=[mock_response("Queued"), mock_response("Queued"), mock_response("Done")],
    ) as mocked_get_job:
        assert job._wait_for_results(
            timeout=backend._provider._client.max_retry_seconds, wait=0.0
        ) == [mock_response("Done")]
        assert mocked_get_job.call_count == 3


def test_result(backend: qss.SuperstaQBackend) -> None:
    job = qss.SuperstaQJob(backend=backend, job_id="123abc")

    expected_results = [{"success": True, "shots": 100, "data": {"counts": {"01": 100}}}]

    expected = qiskit.result.Result.from_dict(
        {
            "results": expected_results,
            "qobj_id": -1,
            "backend_name": "ss_example_qpu",
            "backend_version": gss.API_VERSION,
            "success": True,
            "job_id": "123abc",
        }
    )

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Done"),
    ):
        ans = job.result()

        assert ans.backend_name == expected.backend_name
        assert ans.job_id == expected.job_id


def test_check_if_stopped(backend: qss.SuperstaQBackend) -> None:

    for status in ("Canceled", "Error"):
        job = qss.SuperstaQJob(backend=backend, job_id="123abc")
        job._overall_status = status
        with pytest.raises(gss.SuperstaQUnsuccessfulJobException, match=status):
            job._check_if_stopped()


def test_refresh_job(backend: qss.SuperstaQBackend) -> None:
    job = qss.SuperstaQJob(backend=backend, job_id="123abc,456abc,789abc")

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Queued"),
    ):
        job._refresh_job()
        assert job._overall_status == "Queued"

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Running"),
    ):
        job._refresh_job()
        assert job._overall_status == "Running"

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Done"),
    ):
        job._refresh_job()
        assert job._overall_status == "Done"

    job = qss.SuperstaQJob(backend=backend, job_id="321cba")
    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Error"),
    ):
        job._refresh_job()
        assert job._overall_status == "Error"

    job = qss.SuperstaQJob(backend=backend, job_id="654cba")
    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Canceled"),
    ):
        job._refresh_job()
        assert job._overall_status == "Canceled"


def test_update_status_queue_info(backend: qss.SuperstaQBackend) -> None:
    job = qss.SuperstaQJob(backend=backend, job_id="123abc,456abc,789abc")

    for job_id in job._job_id.split(","):
        job._job_info[job_id] = mock_response("Done")

    job._refresh_job()
    assert job._overall_status == "Done"

    mock_statuses = [
        mock_response("Queued"),
        mock_response("Canceled"),
        mock_response("Canceled"),
    ]
    for index, job_id in enumerate(job._job_id.split(",")):
        job._job_info[job_id] = mock_statuses[index]
    job._update_status_queue_info()
    assert job._overall_status == "Queued"

    mock_statuses = [mock_response("Canceled"), mock_response("Canceled"), mock_response("Queued")]
    for index, job_id in enumerate(job._job_id.split(",")):
        job._job_info[job_id] = mock_statuses[index]
    job._update_status_queue_info()
    assert job._overall_status == "Queued"

    mock_statuses = [mock_response("Done"), mock_response("Done"), mock_response("Error")]
    for index, job_id in enumerate(job._job_id.split(",")):
        job._job_info[job_id] = mock_statuses[index]
    job._update_status_queue_info()
    assert job._overall_status == "Error"


def test_status(backend: qss.SuperstaQBackend) -> None:

    job = qss.SuperstaQJob(backend=backend, job_id="123abc")

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Queued"),
    ):
        assert job.status() == qiskit.providers.JobStatus.QUEUED

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Running"),
    ):
        assert job.status() == qiskit.providers.JobStatus.RUNNING

    with mock.patch(
        "general_superstaq.superstaq_client._SuperstaQClient.get_job",
        return_value=mock_response("Done"),
    ):
        assert job.status() == qiskit.providers.JobStatus.DONE

    job = qss.SuperstaQJob(backend=backend, job_id="123done")
    for status_msg in job.TERMINAL_STATES:
        if status_msg == "Done":
            job._overall_status = "Done"
            assert job.status() == qiskit.providers.JobStatus.DONE
        else:
            job._overall_status = "Canceled"
            assert job.status() == qiskit.providers.JobStatus.CANCELLED


def test_submit(backend: qss.SuperstaQBackend) -> None:
    job = qss.SuperstaQJob(backend=backend, job_id="12345")
    with pytest.raises(NotImplementedError, match="Submit through SuperstaQBackend"):
        job.submit()


def test_eq(backend: qss.SuperstaQBackend) -> None:
    job = qss.SuperstaQJob(backend=backend, job_id="12345")
    assert job != "super.tech"

    job2 = qss.SuperstaQJob(backend=backend, job_id="123456")
    assert job != job2

    job3 = qss.SuperstaQJob(backend=backend, job_id="12345")
    assert job == job3
