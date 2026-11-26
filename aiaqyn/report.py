import json
from pathlib import Path

LABELS = {
    "supported": "Поддержано ревью",
    "needs_clarification": "Уточнить",
    "rejected": "Отклонено",
    "critical": "Критичный",
    "high": "Высокий",
    "medium": "Средний",
    "low": "Низкий",
}


def summarize(data):
    decisions = {d["finding_id"]: d for d in data["review"]["decisions"]}
    supported = [f for f in data["audit"]["findings"] if decisions[f["id"]]["verdict"] == "supported"]
    critical = [f for f in supported if f["severity"] in {"critical", "high"}]
    pending = sum(d["verdict"] == "needs_clarification" for d in decisions.values())
    return {
        "requirements": len(data["inventory"]["requirements"]),
        "supported": len(supported),
        "critical": len(critical),
        "pending": pending,
        "verdict": "Нужны исправления до реализации"
        if critical
        else "Нужно уточнение перед решением"
        if pending
        else "Критичных замечаний не найдено; требуется решение аналитика",
    }


def markdown(data):
    summary = summarize(data)
    m = data["metadata"]
    rows = [
        "# AI AQYN · Ревью требований",
        "",
        f"**{summary['verdict']}**",
        "",
        f"Режим: {m['mode']}. Документ: {m['document']}. Дата: {m['date']}.",
        f"Модель: {m['model']}. Версия агента: {m['version']}. Провайдер: {m['provider']}.",
        f"SHA-256 входа: `{m['sha256']}`. LLM-вызовов: {m['calls']}.",
        "",
        f"Требований: {summary['requirements']}; поддержанных замечаний: {summary['supported']}; "
        f"высоких/критичных: {summary['critical']}; уточнений: {summary['pending']}.",
        "",
        "## Реестр требований",
        "",
        "| ID | ID / раздел источника | Формулировка | Строки |",
        "|---|---|---|---|",
    ]

    def cell(text):
        return str(text).replace("|", "\\|").replace("\n", " ")

    for r in data["inventory"]["requirements"]:
        e = r["evidence"]
        rows.append(
            f"| {cell(r['id'])} | {cell(r['original_id'])} | {cell(r['summary'])} | "
            f"{e['line_start']}–{e['line_end']} |"
        )
    rows += [
        "",
        "## Проверка каждого требования",
        "",
        "| ID | Ясность | Полнота | Проверяемость | Атомарность | Комментарий |",
        "|---|---|---|---|---|---|",
    ]
    for a in data["audit"]["assessments"]:
        rows.append(
            "| "
            + " | ".join(
                cell(a[k])
                for k in ["requirement_id", "clarity", "completeness", "verifiability", "atomicity", "note"]
            )
            + " |"
        )
    rows += [
        "",
        "pass — замечание не найдено; issue — проблема; unknown — недостаточно данных.",
        "",
        "## Оценка набора",
        "",
        data["audit"]["set_assessment"],
        "",
        "## Замечания и решения",
    ]
    decisions = {d["finding_id"]: d for d in data["review"]["decisions"]}
    for f in data["audit"]["findings"]:
        d = decisions[f["id"]]
        rows += [
            "",
            f"### {f['id']} · {f['title']}",
            "",
            f"{LABELS[f['severity']]} · {LABELS[d['verdict']]} · {', '.join(f['requirement_ids'])}",
            "",
            f["explanation"],
            "",
            "Сценарий: " + f["scenario"],
            "",
        ]
        for e in f["evidence"]:
            rows += [
                f"Строки {e['line_start']}–{e['line_end']}:",
                "",
                "> " + e["quote"].replace("\n", "\n> "),
                "",
            ]
        rows += ["Ревью: " + d["reason"], "", "Вопрос: " + f["question"], ""]
        rows += ["- " + option for option in f["repair_options"]]
    rows += ["", "## Формальные свидетели"]
    for w in data["witnesses"]:
        rows += [
            "",
            "### " + w["model"]["finding_id"],
            "",
            "```json",
            json.dumps(w, ensure_ascii=False, indent=2),
            "```",
        ]
    rows += [
        "",
        "## Ограничения",
        "",
        "- Проверяется формальная интерпретация, а не истинность перевода текста в логику.",
        "- Скептический проход использует ту же модель; его решения не являются независимой экспертизой.",
        "- Проверка цитат подтверждает происхождение, но не логическое следование вывода.",
    ]
    rows += ["- " + x for x in data["inventory"]["limitations"] + data["audit"]["limitations"]]
    rows += ["", "## Исходный текст с координатами", "", "```text"]
    rows += [f"{i}: {line}" for i, line in enumerate(data["source"]["lines"], 1)]
    rows += ["```", ""]
    return "\n".join(rows)


def write_reports(output: Path, data):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(data), encoding="utf-8")
    output.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
    # Inert JSON script: escape HTML delimiter and Unicode line separators.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    output.with_suffix(".html").write_text(template.replace("__REPORT_DATA__", payload), encoding="utf-8")
