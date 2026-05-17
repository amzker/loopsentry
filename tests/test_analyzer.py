from loopsentry.analyzer import Analyzer


def test_analyzer_parses_example_logs():
    analyzer = Analyzer("examples/example_logs")
    analyzer.run()

    assert analyzer.blocks
    assert analyzer.stats["count"] > 0
    assert analyzer.stats["total_time"] > 0


def test_analyzer_tracks_cpu_core_stats(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "cpu.jsonl"
    log_file.write_text(
        "\n".join(
            [
                '{"type":"block_started","pid":1,"timestamp":"2026-05-02T00:00:00+00:00","duration_current":0.2,"sys":{"cpu_percent":50.0,"cpu_per_core":[100.0,0.0,50.0,50.0],"memory_mb":10.0,"thread_count":2,"gc_counts":[1,2,3]},"stack":[],"locals":[],"trigger":"x"}',
                '{"type":"block_resolved","pid":1,"timestamp":"2026-05-02T00:00:01+00:00","duration_current":0.2}',
            ]
        ),
        encoding="utf-8",
    )

    analyzer = Analyzer(log_dir)
    analyzer.run()

    assert analyzer.stats["cpu_core_count"] == 4
    assert analyzer.stats["max_cpu_avg"] == 50.0
    assert analyzer.stats["max_cpu_single_core"] == 100.0
    assert analyzer.stats["max_cpu_total"] == 200.0


def test_analyzer_renders_csv_and_html(tmp_path):
    analyzer = Analyzer("examples/example_logs")
    analyzer.run()

    csv_path = tmp_path / "report.csv"
    html_path = tmp_path / "report.html"
    summary_csv_path = tmp_path / "summary.csv"

    analyzer.render_csv(str(csv_path))
    analyzer.render_html(str(html_path))
    analyzer.render_summary_csv(str(summary_csv_path))

    assert csv_path.exists()
    assert html_path.exists()
    assert summary_csv_path.exists()

    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("ID,Type,Timestamp")
    assert "UserLocation" in header
    assert "BlockingLocation" in header

    summary_header = summary_csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert summary_header == "Rank,Type,Count,Location,BlockingLocation,Hint,CulpritFrame"

    html = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "CPU Timeline" in html
    assert "Block Timeline" in html


def test_analyzer_prints_summary(capsys):
    analyzer = Analyzer("examples/example_logs")
    analyzer.run()
    analyzer.print_summary()
    captured = capsys.readouterr()
    assert "LoopSentry Culprit Digest" in captured.out
