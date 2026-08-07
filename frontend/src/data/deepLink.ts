import { DiagramData } from './types';

/** Parse repeated or comma-separated Kotlin element names from `targets` URL parameters. */
export function parseTargetNames(search: string): string[] {
  const values = new URLSearchParams(search).getAll('targets');
  return [...new Set(values.flatMap((value) => value.split(',')).map((name) => name.trim()).filter(Boolean))];
}

/** Resolve element display names to the stable refs used by diagram data, preserving input order. */
export function resolveElementNames(data: DiagramData, names: readonly string[]): string[] {
  const wantedNames = new Set(names);
  const refByName = new Map<string, string>();
  for (const element of data.elements.values()) {
    if (wantedNames.has(element.name) && !refByName.has(element.name)) {
      refByName.set(element.name, element.ref);
    }
  }
  return names.flatMap((name) => {
    const ref = refByName.get(name);
    return ref ? [ref] : [];
  });
}
