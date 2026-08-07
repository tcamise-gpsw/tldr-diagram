import { Connector, DiagramData, Element } from './types';

export interface ComponentFocus {
  elements: Element[];
  connectors: Connector[];
}

/**
 * Build a cross-hierarchy focus view containing one or more target components, every direct
 * class-level neighbor of any target, and every class-level edge among the resulting nodes.
 */
export function computeComponentFocus(
  data: DiagramData,
  centerRefs: string | readonly string[],
): ComponentFocus {
  const requestedRefs = typeof centerRefs === 'string' ? [centerRefs] : centerRefs;
  const targets = new Set(
    requestedRefs.filter((ref) => {
      const element = data.elements.get(ref);
      return element !== undefined && !element.has_view;
    }),
  );
  if (targets.size === 0) return { elements: [], connectors: [] };

  const isClassConnector = (connector: Connector): boolean => {
    const source = data.elements.get(connector.source);
    const target = data.elements.get(connector.target);
    return !!source
      && !!target
      && !source.has_view
      && !target.has_view
      && (!connector.level || connector.level === 'class');
  };

  const members = new Set<string>(targets);
  for (const connector of data.connectors) {
    if (!isClassConnector(connector)) continue;
    if (targets.has(connector.source)) members.add(connector.target);
    if (targets.has(connector.target)) members.add(connector.source);
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
