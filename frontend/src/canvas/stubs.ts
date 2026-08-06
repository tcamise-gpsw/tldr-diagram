import { DiagramData } from '../data/types';
import { ViewLayout } from './layout';

/**
 * Describes one external connector stub: a dashed line + label drawn from a node
 * edge toward the canvas boundary, representing connections that cross the current
 * view boundary.
 */
export interface ExternalStub {
  /** Stable key shared by a collapsed group and all of its expanded targets. */
  groupKey: string;
  /** Ref of the node this stub originates from. */
  nodeRef: string;
  /** Human-readable name of the external group being connected to/from. */
  targetGroup: string;
  /** When count === 1, the actual target element name. */
  targetName?: string;
  /** Ref of the individual target when this stub represents one connector. */
  targetRef?: string;
  /** True when an aggregated group is displaying its individual targets. */
  expanded?: boolean;
  /** Whether this stub represents connections going out or coming in. */
  direction: 'outbound' | 'inbound';
  /** Number of connectors aggregated into this stub. */
  count: number;
  /** Angle in radians for the stub direction (0 = right, π = left). */
  angle: number;
  /** Node center X in world coordinates. */
  nodeX: number;
  /** Node center Y in world coordinates. */
  nodeY: number;
  /** Node width in world coordinates. */
  nodeWidth: number;
  /** Node height in world coordinates. */
  nodeHeight: number;
}

interface StubTarget {
  ref: string;
  name: string;
}

type StubAccum = Omit<ExternalStub, 'angle' | 'count' | 'targetName' | 'targetRef' | 'expanded'> & {
  targets: Map<string, StubTarget>;
};

export const EXTERNAL_STUB_LENGTH = 50;
export const EXTERNAL_STUB_GAP = 6;

export interface ExternalStubGeometry {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
}

/** Shared line geometry used by both rendering and hit testing. */
export function getExternalStubGeometry(stub: ExternalStub): ExternalStubGeometry {
  const cosA = Math.cos(stub.angle);
  const sinA = Math.sin(stub.angle);
  const halfW = stub.nodeWidth / 2;
  const halfH = stub.nodeHeight / 2;
  const edgeDist = Math.abs(sinA) < 1e-10
    ? halfW
    : Math.abs(cosA) < 1e-10
      ? halfH
      : Math.min(halfW / Math.abs(cosA), halfH / Math.abs(sinA));

  return {
    startX: stub.nodeX + cosA * (edgeDist + EXTERNAL_STUB_GAP),
    startY: stub.nodeY + sinA * (edgeDist + EXTERNAL_STUB_GAP),
    endX: stub.nodeX + cosA * (edgeDist + EXTERNAL_STUB_GAP + EXTERNAL_STUB_LENGTH),
    endY: stub.nodeY + sinA * (edgeDist + EXTERNAL_STUB_GAP + EXTERNAL_STUB_LENGTH),
  };
}

/**
 * Walk up the placement hierarchy from `elementRef` to find the direct child of
 * `viewRef` that contains (or is) `elementRef`.
 *
 * Returns the ref of that direct child, or `null` if `elementRef` is not a
 * descendant of `viewRef`.
 *
 * Uses `element.placements[0].parent` exclusively — consistent with the
 * placement-based externality semantics used throughout the app, and works for
 * both flat views (element IS a direct child) and hierarchical views (element is a
 * nested descendant inside a visible group node).
 */
function getVisibleNodeAncestor(
  elementRef: string,
  viewRef: string,
  data: DiagramData
): string | null {
  let current = elementRef;
  const visited = new Set<string>();

  while (!visited.has(current)) {
    visited.add(current);
    const elem = data.elements.get(current);
    if (!elem) return null;

    const parentRef = elem.placements[0]?.parent ?? 'root';
    // current is a direct child of viewRef → this is the visible node
    if (parentRef === viewRef) return current;
    // reached the tree root without crossing viewRef → not in this view
    if (parentRef === 'root' && viewRef !== 'root') return null;
    current = parentRef;
  }
  return null; // cycle guard
}

/**
 * Compute external stub descriptors for all nodes visible in the current view.
 *
 * Works for both flat views (visible nodes are leaf elements) **and** hierarchical
 * views (visible nodes are group nodes whose descendants carry the actual connectors).
 *
 * A connector is "external" when exactly one of its endpoints is a descendant of
 * `viewRef`. The stub is attributed to the visible node (a direct child of `viewRef`)
 * that contains the in-view endpoint, found by walking `placements` ancestry.
 *
 * Groups by (nodeRef, resolvedTargetGroupName, direction) so that multiple
 * connections to the same external group are collapsed into a single stub with
 * a count > 1.
 *
 * Angles are spread per node so stubs don't overlap:
 *   - Outbound stubs fan out from the right side (base angle 0).
 *   - Inbound stubs fan out from the left side (base angle π).
 *   - Spread range is ±30° (π/6) per side.
 */
export function computeExternalStubs(
  data: DiagramData,
  viewRef: string,
  layout: ViewLayout,
  autoExpandForNode?: string,
): ExternalStub[] {
  const layoutNodeRefs = new Set(layout.nodes.map((node) => node.ref));
  const layoutNodeByRef = new Map(layout.nodes.map((node) => [node.ref, node]));
  const groups = new Map<string, StubAccum>();

  for (const conn of data.connectors) {
    const sourceAncestor = getVisibleNodeAncestor(conn.source, viewRef, data);
    const targetAncestor = getVisibleNodeAncestor(conn.target, viewRef, data);
    const sourceInView = sourceAncestor !== null && layoutNodeRefs.has(sourceAncestor);
    const targetInView = targetAncestor !== null && layoutNodeRefs.has(targetAncestor);
    if (sourceInView === targetInView) continue;

    const nodeRef = sourceInView ? sourceAncestor! : targetAncestor!;
    const direction = sourceInView ? 'outbound' : 'inbound';
    const otherEndpointRef = sourceInView ? conn.target : conn.source;
    const otherElement = data.elements.get(otherEndpointRef);
    const otherParentRef = otherElement?.placements[0]?.parent ?? 'root';
    const targetGroup = data.elements.get(otherParentRef)?.name ?? otherParentRef;
    const groupKey = `${nodeRef}|${otherParentRef}|${direction}`;
    const existing = groups.get(groupKey);

    if (existing) {
      existing.targets.set(otherEndpointRef, { ref: otherEndpointRef, name: otherElement?.name ?? otherEndpointRef });
      continue;
    }

    const layoutNode = layoutNodeByRef.get(nodeRef)!;
    groups.set(groupKey, {
      groupKey,
      nodeRef,
      targetGroup,
      direction,
      nodeX: layoutNode.x,
      nodeY: layoutNode.y,
      nodeWidth: layoutNode.width,
      nodeHeight: layoutNode.height,
      targets: new Map([[otherEndpointRef, { ref: otherEndpointRef, name: otherElement?.name ?? otherEndpointRef }]]),
    });
  }

  const stubsByNode = new Map<string, Array<Omit<ExternalStub, 'angle'>>>();
  for (const group of groups.values()) {
    const { targets, ...base } = group;
    const targetList = [...targets.values()];
    const shouldExpand = autoExpandForNode === group.nodeRef && targetList.length > 1;
    const stubs = shouldExpand
      ? targetList.map((target) => ({
          ...base,
          targetName: target.name,
          targetRef: target.ref,
          count: 1,
          expanded: true,
        }))
      : [{
          ...base,
          targetName: targetList.length === 1 ? targetList[0].name : undefined,
          targetRef: targetList.length === 1 ? targetList[0].ref : undefined,
          count: targetList.length,
          expanded: false,
        }];
    const list = stubsByNode.get(group.nodeRef) ?? [];
    list.push(...stubs);
    stubsByNode.set(group.nodeRef, list);
  }

  const spreadRange = Math.PI / 3;
  const result: ExternalStub[] = [];
  for (const stubs of stubsByNode.values()) {
    const assignAngles = (
      list: Array<Omit<ExternalStub, 'angle'>>,
      baseAngle: number,
    ): void => {
      list.forEach((stub, index) => {
        const offset = list.length === 1
          ? 0
          : ((index / (list.length - 1)) - 0.5) * spreadRange;
        result.push({ ...stub, angle: baseAngle + offset });
      });
    };
    assignAngles(stubs.filter((stub) => stub.direction === 'outbound'), 0);
    assignAngles(stubs.filter((stub) => stub.direction === 'inbound'), Math.PI);
  }
  return result;
}
