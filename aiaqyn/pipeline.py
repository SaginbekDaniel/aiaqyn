from .schema import Audit, Formalizations, Inventory, Review
from .solver import solve_witness


class Pipeline:
    def __init__(self, provider, progress=print):
        self.provider, self.progress = provider, progress

    def run(self, doc):
        source = "\n<document>\n" + doc.numbered() + "\n</document>"
        self.progress("1/4 Извлечение требований и точных цитат")
        inventory = self.provider.generate(
            "Выдели ВСЕ атомарные нормативные требования, включая таблицы API, "
            "приёмку, данные, NFR. Не включай пустые поля согласования и чек-лист как требования продукта. "
            "Сохрани original_id (либо раздел для ненумерованных), назначь уникальные R001... "
            "Один составной пункт может дать несколько требований. Отметь ограничения извлечения." + source,
            Inventory,
        )
        ids = [r.id for r in inventory.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate requirement IDs")
        for requirement in inventory.requirements:
            doc.verify(requirement.evidence)
        context = source + "\n<inventory>" + inventory.model_dump_json() + "</inventory>"
        self.progress("2/4 Проверка каждого требования и связей документа")
        audit = self.provider.generate(
            "Проверь каждое требование по ясности, полноте, проверяемости и "
            "атомарности. Дай ровно одну assessment на каждый id. Затем сопоставь разные разделы: "
            "бизнес-правила, API, сценарии приёмки. Для каждого дефекта укажи сценарий, вопрос владельцу "
            "и альтернативы исправления, не выбирай бизнес-правило за него. Для противоречия нужны "
            "минимум два разных требования и две цитаты. Не придумывай дефект ради количества. "
            "Непроверяемое помечай unknown. Сформируй оценку набора и ограничения." + context,
            Audit,
        )
        assessed = [a.requirement_id for a in audit.assessments]
        if sorted(assessed) != sorted(ids):
            raise ValueError("Incomplete or duplicate per-requirement assessment")
        finding_ids = [f.id for f in audit.findings]
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("Duplicate finding IDs")
        for f in audit.findings:
            if not set(f.requirement_ids) <= set(ids):
                raise ValueError("Finding cites unknown requirement")
            for evidence in f.evidence:
                doc.verify(evidence)
            if f.category == "contradiction" and (len(set(f.requirement_ids)) < 2 or len(f.evidence) < 2):
                raise ValueError("Contradiction lacks two-sided evidence")
        self.progress("3/4 Скептическое ревью замечаний")
        review = self.provider.generate(
            "Проведи скептическую проверку каждого замечания. Ищи допустимое "
            "толкование, исключение или уточнение в другом разделе. supported только если вывод следует "
            "из текста; иначе needs_clarification или rejected. Совпадение цитаты не доказывает вывод. "
            "Ровно одно решение на каждый finding_id. Ничего не добавляй.\n"
            + context
            + "\n<audit>"
            + audit.model_dump_json()
            + "</audit>",
            Review,
        )
        if sorted(d.finding_id for d in review.decisions) != sorted(finding_ids):
            raise ValueError("Reviewer did not cover every finding exactly once")
        decisions = {d.finding_id: d for d in review.decisions}
        supported = [f for f in audit.findings if decisions[f.id].verdict == "supported"]
        self.progress("4/4 Поиск исполнимых свидетелей противоречия")
        formal = self.provider.generate(
            "Для поддержанных числовых/логических противоречий предложи "
            "конечную целочисленную модель. Если не подходит — пропусти. На ОДНИХ входах два требования "
            "дают разные значения одного output_name. left/right ссылаются на разные requirement_id "
            "из замечания. guard описывает условия применимости. Expr: variable+offset, "
            "variable=null означает константу. Boolean кодируй 0/1, месяцы целыми. Не добавляй "
            "предположений о поведении, которых нет в тексте; явно перечисли assumptions и единицы. "
            "Модель — проверяемая гипотеза перевода, не доказательство естественного языка.\n"
            + context
            + "\nSupported findings:\n"
            + "\n".join(f.model_dump_json() for f in supported),
            Formalizations,
        )
        witnesses = []
        by_id = {f.id: f for f in supported}
        seen = set()
        for model in formal.models:
            finding = by_id.get(model.finding_id)
            if not finding or finding.category != "contradiction":
                raise ValueError("Formalization is not tied to a supported contradiction")
            if model.finding_id in seen:
                raise ValueError("Duplicate witness model")
            seen.add(model.finding_id)
            pair = {model.left.requirement_id, model.right.requirement_id}
            if len(pair) != 2 or not pair <= set(finding.requirement_ids):
                raise ValueError("Invalid formalization evidence mapping")
            witnesses.append({"model": model.model_dump(), "result": solve_witness(model)})
        return {
            "inventory": inventory.model_dump(),
            "audit": audit.model_dump(),
            "review": review.model_dump(),
            "witnesses": witnesses,
        }
