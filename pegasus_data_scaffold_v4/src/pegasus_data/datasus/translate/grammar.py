from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .registry import TranslationRegistry, VariableTranslation


class TranslationGrammarError(ValueError):
    pass


@dataclass
class _Builder:
    scope: str
    variable: str
    kind: str
    label: str
    value_map: dict[str, str]
    rules: list[str]
    aliases: list[str]
    sources: list[str]

    def freeze(self) -> VariableTranslation:
        return VariableTranslation(
            scope=self.scope,
            variable=self.variable,
            kind=self.kind,
            label=self.label,
            value_map=dict(self.value_map),
            rules=list(self.rules),
            aliases=list(self.aliases),
            sources=list(self.sources),
        )


def parse_translation_grammar(text: str) -> TranslationRegistry:
    entries: list[VariableTranslation] = []
    current: _Builder | None = None
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        head = line[0]
        body = line[1:].strip()
        if head == '$':
            if current is not None:
                entries.append(current.freeze())
            parts = body.split(maxsplit=2)
            if len(parts) < 3:
                raise TranslationGrammarError(f'Line {line_no}: global variable line must be "$ VAR KIND LABEL"')
            current = _Builder(scope='GLOBAL', variable=parts[0], kind=parts[1], label=parts[2], value_map={}, rules=[], aliases=[], sources=[])
            continue
        if head == '@':
            if current is not None:
                entries.append(current.freeze())
            parts = body.split(maxsplit=3)
            if len(parts) < 4:
                raise TranslationGrammarError(f'Line {line_no}: scoped variable line must be "@ SCOPE VAR KIND LABEL"')
            current = _Builder(scope=parts[0], variable=parts[1], kind=parts[2], label=parts[3], value_map={}, rules=[], aliases=[], sources=[])
            continue
        if current is None:
            raise TranslationGrammarError(f'Line {line_no}: directive without active variable block')
        if head == '=':
            parts = body.split(maxsplit=1)
            if len(parts) < 2:
                raise TranslationGrammarError(f'Line {line_no}: value map line must be "= RAW LABEL"')
            current.value_map[parts[0]] = parts[1]
        elif head == '>':
            current.rules.extend(token for token in body.split() if token)
        elif head == '~':
            current.aliases.extend(token for token in body.split() if token)
        elif head == '%':
            current.sources.extend(token for token in body.split() if token)
        else:
            raise TranslationGrammarError(f'Line {line_no}: unknown directive {head!r}')
    if current is not None:
        entries.append(current.freeze())
    return TranslationRegistry(entries)


def parse_translation_grammar_file(path: str | Path) -> TranslationRegistry:
    return parse_translation_grammar(Path(path).read_text(encoding='utf-8'))


def emit_translation_grammar(registry: TranslationRegistry) -> str:
    lines: list[str] = []
    for entry in sorted(registry.entries, key=lambda e: (e.scope.upper(), e.variable.upper())):
        if entry.scope.upper() == 'GLOBAL':
            lines.append(f'$ {entry.variable} {entry.kind} {entry.label}')
        else:
            lines.append(f'@ {entry.scope} {entry.variable} {entry.kind} {entry.label}')
        if entry.aliases:
            lines.append('~ ' + ' '.join(entry.aliases))
        if entry.rules:
            lines.append('> ' + ' '.join(entry.rules))
        if entry.sources:
            lines.append('% ' + ' '.join(entry.sources))
        for raw, label in sorted(entry.value_map.items()):
            lines.append(f'= {raw} {label}')
        lines.append('')
    return '\n'.join(lines).rstrip() + ('\n' if lines else '')
