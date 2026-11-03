"""Render the saved experiment without retraining or changing model selection."""
import json
from pathlib import Path

ROOT = Path(__file__).parent


def render(report):
    lines = ['# MatchPlan: шесть моделей и две базы', '',
             'Premier League 2015/16. Ниже сохранённые результаты одного временного эксперимента.', '',
             '| Часть | Матчи | Срезы | Начало | Конец |', '|---|---:|---:|---|---|']
    for name, split in report['splits'].items():
        lines.append(f'| {name} | {split["matches"]} | {split["states"]} | {split["date_from"]} | {split["date_to"]} |')
    lines += ['', 'Срезы одного матча и два ракурса зависимы; это не дополнительные независимые матчи.', '',
              '| Модель | Validation Log Loss | Test Log Loss | Test Brier | Test Accuracy | Test AUC macro OvR |',
              '|---|---:|---:|---:|---:|---:|']
    for name, result in report['models'].items():
        lines.append(f'| {name} | {result["validation"]["log_loss"]:.4f} | {result["test"]["log_loss"]:.4f} | '
                     f'{result["test"]["brier_multiclass"]:.4f} | {result["test"]["accuracy"]:.3f} | {result["test"].get("roc_auc_macro_ovr", float("nan")):.4f} |')
    for key, title in [('baseline_score_time', 'База: счёт, время, численность, поле'),
                       ('baseline_training_class_prior', 'База: частоты классов train')]:
        result = report[key]
        lines.append(f'| {title} | — | {result["log_loss"]:.4f} | {result["brier_multiclass"]:.4f} | {result["accuracy"]:.3f} | {result.get("roc_auc_macro_ovr", float("nan")):.4f} |')
    lines += ['', f'**Выбор по валидации среди шести: {report["selected_by_validation"]}.** '
              'Результаты теста не использовались для замены выбранной модели.', '',
              'Log Loss и Brier: меньше лучше. Accuracy приведена как вспомогательная метрика.']
    if report['baseline_score_time']['log_loss'] < min(r['test']['log_loss'] for r in report['models'].values()):
        lines += ['', '**На этом тесте базовая модель лучше всех шести полных моделей по Log Loss. '
                  'Преимущество усложнения не подтверждено.** Малые различия не доказывают статистического превосходства.']
    lines += ['', '## Архитектуры и фактическое обучение', '',
              '| Сеть | Параметры | Лучшая эпоха | Эпох выполнено |', '|---|---:|---:|---:|']
    for name in ('MLP', 'Transformer', 'LSTM'):
        config = report['models'][name]['configuration']
        lines.append(f'| {name} | {config["parameters"]} | {config["best_epoch"]} | {config["epochs_run"]} |')
    lines += ['', '## Ограничения', '',
              'Один исторический сезон. Общие команды и коррелированные срезы ограничивают независимость. '
              'Никакого доказанного причинного эффекта тактических рекомендаций. '
              'Предматчевые вероятности не учитывают полноценные рейтинги команд и стартовых игроков. '
              'Все метрики, интервалы, эпохи, версии библиотек и списки матчей находятся в ml_results.json; '
              'все тестовые вероятности — в test_predictions.csv.', '',
              f'Seed: {report["seed"]}. Подготовка и обучение: {report["elapsed_seconds"]:.1f} секунд.']
    (ROOT / 'reports' / 'ML_REPORT.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    render(json.loads((ROOT / 'reports/ml_results.json').read_text(encoding='utf-8')))
