import { LayoutNode } from './layout';
import { ExternalStub, getExternalStubGeometry } from './stubs';

export const PAN_THRESHOLD = 5;

export function hitTestNodes(worldX: number, worldY: number, nodes: LayoutNode[]): string | null {
  // Test in reverse order (last drawn = visually on top = first hit)
  for (let i = nodes.length - 1; i >= 0; i--) {
    const node = nodes[i];
    const left = node.x - node.width / 2;
    const right = node.x + node.width / 2;
    const top = node.y - node.height / 2;
    const bottom = node.y + node.height / 2;

    if (worldX >= left && worldX <= right && worldY >= top && worldY <= bottom) {
      return node.ref;
    }
  }

  return null;
}

export function isDrag(startX: number, startY: number, endX: number, endY: number): boolean {
  const dx = endX - startX;
  const dy = endY - startY;
  const distance = Math.sqrt(dx * dx + dy * dy);
  return distance > PAN_THRESHOLD;
}

export function hitTestGroupIcon(worldX: number, worldY: number, nodes: LayoutNode[]): string | null {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const node = nodes[i];
    if (!node.isGroup) continue;
    
    // Icon is drawn at (node.x + width/2 - 16, node.y - height/2 + 16)
    // Hit radius of 16px
    const iconX = node.x + node.width / 2 - 16;
    const iconY = node.y - node.height / 2 + 16;
    
    const dx = worldX - iconX;
    const dy = worldY - iconY;
    if (dx * dx + dy * dy <= 256) { // 16^2
      return node.ref;
    }
  }
  return null;
}

export function hitTestFocusIcon(worldX: number, worldY: number, nodes: LayoutNode[]): string | null {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const node = nodes[i];
    if (node.isGroup) continue;
    // Same position as group icon: top-right corner
    const iconX = node.x + node.width / 2 - 16;
    const iconY = node.y - node.height / 2 + 16;
    const dx = worldX - iconX;
    const dy = worldY - iconY;
    if (dx * dx + dy * dy <= 256) { // 16px radius
      return node.ref;
    }
  }
  return null;
}

export function hitTestExternalStubs(
  worldX: number,
  worldY: number,
  stubs: ExternalStub[],
  tolerance = 8,
): string | null {
  for (let index = stubs.length - 1; index >= 0; index--) {
    const stub = stubs[index];
    const { startX, startY, endX, endY } = getExternalStubGeometry(stub);
    const dx = endX - startX;
    const dy = endY - startY;
    const lengthSquared = dx * dx + dy * dy;
    const projection = lengthSquared === 0
      ? 0
      : Math.max(0, Math.min(1, ((worldX - startX) * dx + (worldY - startY) * dy) / lengthSquared));
    const closestX = startX + projection * dx;
    const closestY = startY + projection * dy;
    const distanceSquared = (worldX - closestX) ** 2 + (worldY - closestY) ** 2;
    if (distanceSquared <= tolerance * tolerance) return stub.groupKey;
  }
  return null;
}
