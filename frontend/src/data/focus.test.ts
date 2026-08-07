import { describe, expect, it } from 'vitest';
import { computeComponentFocus } from './focus';
import { Connector, DiagramData, Element, ViewNode } from './types';

function element(ref: string, name: string, hasView = false): Element {
  return {
    ref,
    name,
    kind: hasView ? 'group' : 'class',
    description: '',
    technology: 'Kotlin',
    has_view: hasView,
    placements: [{ parent: 'root' }],
  };
}

function data(elements: Element[], connectors: Connector[]): DiagramData {
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
    connectors,
    viewTree: { nodes: new Map([['root', root]]), root },
  };
}

describe('computeComponentFocus', () => {
  it('returns direct neighbors plus every class-level edge between the displayed components', () => {
    const diagram = data(
      [
        element('manager', 'CameraConnectionManager'),
        element('controller', 'CameraConnectionController'),
        element('facade', 'DefaultCameraConnectionsFacade'),
        element('ble', 'CameraBleConnection'),
        element('gateway', 'CameraGateway'),
        element('ports', 'Ports', true),
      ],
      [
        { id: 'c1', source: 'facade', target: 'manager', view: 'class', level: 'class', relationship: 'dependency' },
        { id: 'c2', source: 'manager', target: 'controller', view: 'class', level: 'class', relationship: 'inheritance' },
        { id: 'c3', source: 'controller', target: 'ble', view: 'class', level: 'class', relationship: 'dependency' },
        { id: 'c4', source: 'manager', target: 'ble', view: 'class', level: 'class', relationship: 'dependency' },
        { id: 'c5', source: 'ble', target: 'gateway', view: 'class', level: 'class', relationship: 'dependency' },
        { id: 'aggregated', source: 'manager', target: 'ports', view: 'root', level: 'root', relationship: 'dependency' },
      ],
    );

    const focus = computeComponentFocus(diagram, 'manager');

    expect(focus.elements.map((item) => item.ref).sort()).toEqual([
      'ble',
      'controller',
      'facade',
      'manager',
    ]);
    expect(focus.connectors.map((item) => item.id).sort()).toEqual(['c1', 'c2', 'c3', 'c4']);
  });

  it('unions direct neighbors for multiple targets and includes every edge among them', () => {
    const diagram = data(
      [
        element('target-a', 'TargetA'),
        element('target-b', 'TargetB'),
        element('neighbor-a', 'NeighborA'),
        element('neighbor-b', 'NeighborB'),
        element('shared', 'SharedNeighbor'),
        element('outside', 'Outside'),
      ],
      [
        { id: 'a-neighbor', source: 'target-a', target: 'neighbor-a', view: 'class', level: 'class' },
        { id: 'a-shared', source: 'target-a', target: 'shared', view: 'class', level: 'class' },
        { id: 'b-neighbor', source: 'neighbor-b', target: 'target-b', view: 'class', level: 'class' },
        { id: 'b-shared', source: 'target-b', target: 'shared', view: 'class', level: 'class' },
        { id: 'between-neighbors', source: 'neighbor-a', target: 'neighbor-b', view: 'class', level: 'class' },
        { id: 'outside', source: 'neighbor-a', target: 'outside', view: 'class', level: 'class' },
      ],
    );

    const focus = computeComponentFocus(diagram, ['target-a', 'target-b']);

    expect(focus.elements.map((item) => item.ref).sort()).toEqual([
      'neighbor-a',
      'neighbor-b',
      'shared',
      'target-a',
      'target-b',
    ]);
    expect(focus.connectors.map((item) => item.id).sort()).toEqual([
      'a-neighbor',
      'a-shared',
      'b-neighbor',
      'b-shared',
      'between-neighbors',
    ]);
  });

  it('returns empty for groups', () => {
    const diagram = data([element('ports', 'Ports', true)], []);
    expect(computeComponentFocus(diagram, 'ports')).toEqual({ elements: [], connectors: [] });
  });
});
