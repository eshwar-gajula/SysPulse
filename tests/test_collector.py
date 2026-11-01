import time

from syspulse.collector import SystemCollector


def test_collection_is_read_only_bounded_and_never_includes_command_lines():
    collector = SystemCollector()
    first = collector.collect()
    assert first.timestamp.endswith("Z")
    assert first.logical_cpus >= 1
    assert first.metrics.process_count >= 1
    assert len(first.processes) <= 30
    assert "cmdline" not in first.model_dump_json()

    time.sleep(0.12)
    second = collector.collect()
    assert second.metrics.cpu_percent is None or 0 <= second.metrics.cpu_percent <= 100
    assert 0 <= second.metrics.memory_percent <= 100
    assert (
        second.metrics.network_receive_bytes_per_second is None
        or second.metrics.network_receive_bytes_per_second >= 0
    )
    assert all(process.pid > 0 for process in second.processes)


def test_process_name_controls_are_removed():
    from syspulse.collector import _clean_process_name

    assert _clean_process_name("python\n--secret\x00") == "python--secret"
    assert _clean_process_name("") == "Unknown process"
