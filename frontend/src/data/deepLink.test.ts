import { describe, expect, it } from 'vitest';
import { parseTargetNames, resolveElementNames } from './deepLink';
import { DiagramData, Element, ViewNode } from './types';

function diagram(elements: Element[]): DiagramData {
  const root: ViewNode = {
    ref: 'root',
    name: 'Root',
    kind: 'root',
    description: '',
    has_view: true,
    children: elements.map((item) => item.ref),
    parent: 'root',
  };
  return {
    elements: new Map(elements.map((item) => [item.ref, item])),
    connectors: [],
    viewTree: { nodes: new Map([['root', root]]), root },
  };
}

function element(ref: string, name: string): Element {
  return {
    ref,
    name,
    kind: 'class',
    description: '',
    technology: 'Kotlin',
    has_view: false,
    placements: [{ parent: 'root' }],
  };
}

describe('multi-target deep links', () => {
  it('parses any number of comma-separated target names', () => {
    expect(parseTargetNames('?view=data--camera&targets=TargetA,TargetB,TargetC')).toEqual([
      'TargetA',
      'TargetB',
      'TargetC',
    ]);
  });

  it('accepts one targets parameter per element for readable URLs', () => {
    expect(parseTargetNames('?targets=TargetA&targets=TargetB&targets=TargetC')).toEqual([
      'TargetA',
      'TargetB',
      'TargetC',
    ]);
  });

  it('trims, deduplicates, and ignores empty target names', () => {
    expect(parseTargetNames('?targets=TargetA,%20TargetB,,TargetA')).toEqual(['TargetA', 'TargetB']);
  });

  it('resolves target names to stable element refs and ignores unknown names', () => {
    const data = diagram([
      element('path/a.kt::TargetA', 'TargetA'),
      element('path/b.kt::TargetB', 'TargetB'),
    ]);

    expect(resolveElementNames(data, ['TargetB', 'Missing', 'TargetA'])).toEqual([
      'path/b.kt::TargetB',
      'path/a.kt::TargetA',
    ]);
  });

  it('preserves the existing first-match behavior when element names collide', () => {
    const data = diagram([
      element('path/first.kt::Duplicate', 'Duplicate'),
      element('path/second.kt::Duplicate', 'Duplicate'),
    ]);

    expect(resolveElementNames(data, ['Duplicate'])).toEqual(['path/first.kt::Duplicate']);
  });
});
