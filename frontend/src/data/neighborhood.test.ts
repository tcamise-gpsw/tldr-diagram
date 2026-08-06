import { describe, expect, it } from 'vitest';
import { computeComponentNeighborhood } from './neighborhood';
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

describe('computeComponentNeighborhood', () => {
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

    const neighborhood = computeComponentNeighborhood(diagram, 'manager');

    expect(neighborhood.elements.map((item) => item.ref).sort()).toEqual([
      'ble',
      'controller',
      'facade',
      'manager',
    ]);
    expect(neighborhood.connectors.map((item) => item.id).sort()).toEqual(['c1', 'c2', 'c3', 'c4']);
  });

  it('returns an empty neighborhood for groups', () => {
    const diagram = data([element('ports', 'Ports', true)], []);
    expect(computeComponentNeighborhood(diagram, 'ports')).toEqual({ elements: [], connectors: [] });
  });
});
