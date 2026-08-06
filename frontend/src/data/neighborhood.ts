import { Connector, DiagramData, Element } from './types';

export interface ComponentNeighborhood {
  elements: Element[];
  connectors: Connector[];
}

/** Build a cross-hierarchy view containing one component and every direct class-level neighbor. */
export function computeComponentNeighborhood(
  data: DiagramData,
  centerRef: string,
): ComponentNeighborhood {
  const center = data.elements.get(centerRef);
  if (!center || center.has_view) return { elements: [], connectors: [] };

  const isClassConnector = (connector: Connector): boolean => {
    const source = data.elements.get(connector.source);
    const target = data.elements.get(connector.target);
    return !!source
      && !!target
      && !source.has_view
      && !target.has_view
      && (!connector.level || connector.level === 'class');
  };

  const members = new Set<string>([centerRef]);
  for (const connector of data.connectors) {
    if (!isClassConnector(connector)) continue;
    if (connector.source === centerRef) members.add(connector.target);
    if (connector.target === centerRef) members.add(connector.source);
  }

  const connectors: Connector[] = [];
  const seen = new Set<string>();
  for (const connector of data.connectors) {
    if (!isClassConnector(connector)) continue;
    if (!members.has(connector.source) || !members.has(connector.target)) continue;
    const key = `${connector.source}|${connector.target}|${connector.relationship ?? connector.label ?? ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    connectors.push(connector);
  }

  return {
    elements: [...members]
      .map((ref) => data.elements.get(ref))
      .filter((element): element is Element => element !== undefined),
    connectors,
  };
}
