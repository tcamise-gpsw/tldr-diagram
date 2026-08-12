import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import logoUrl from './assets/logo.png';
import { loadDiagramData, getViewElements, getViewConnectors, getDescendantRefs } from './data/loader';
import { DiagramData } from './data/types';
import { computeExternalStubs } from './canvas/stubs';
import { computeComponentFocus } from './data/focus';
import { parseTargetNames, resolveElementNames } from './data/deepLink';
import { getOrComputeLayout, invalidateLayout, ViewLayout } from './canvas/layout';
import { CanvasViewport } from './canvas/CanvasViewport';
import { Toolbar } from './components/Toolbar';
import { Tooltip } from './components/Tooltip';
import { SidePanel } from './components/SidePanel';
import { startTransition, startExitTransition, TransitionState } from './canvas/animation';
import './styles.css';

export const App: React.FC = () => {
  const [data, setData] = useState<DiagramData | null>(null);
  const [sourceRoot, setSourceRoot] = useState<string | null>(null);
  const [navigationStack, setNavigationStack] = useState<string[]>(() => {
    const view = new URLSearchParams(window.location.search).get('view');
    if (!view || view === 'root') return ['root'];
    const segs = view.split('--');
    return ['root', ...segs.map((_, i) => segs.slice(0, i + 1).join('--'))];
  });
  const currentView = navigationStack[navigationStack.length - 1];
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  // Capture raw URL params once at mount — before the sync effect wipes them
  const [initialSelected] = useState(() => new URLSearchParams(window.location.search).get('selected'));
  const [initialFocus] = useState(() => new URLSearchParams(window.location.search).get('focus'));
  const [initialTargetNames] = useState(() => parseTargetNames(window.location.search));
  const [panelCollapsed, setPanelCollapsed] = useState(() => new URLSearchParams(window.location.search).get('panel') === 'collapsed');
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [hoveredGroupIcon, setHoveredGroupIcon] = useState<string | null>(null);
  const [hoveredFocusIcon, setHoveredFocusIcon] = useState<string | null>(null);
  const [hoveredSourceIcon, setHoveredSourceIcon] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [showExternalStubs, setShowExternalStubs] = useState(true);
  const [focusedNode, setFocusedNode] = useState<string | null>(null);
  const [focusTargetRefs, setFocusTargetRefs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [pendingNavigation, setPendingNavigation] = useState<{
    transitionState: TransitionState;
    action: () => void;
  } | null>(null);
  // Ref updated every render so the keydown handler can read the latest layout
  // without stale-closure issues (layout is computed in the render body, not state).
  const layoutRef = useRef<ViewLayout>({ nodes: [], edges: [], width: 0, height: 0 });

  // Load diagram data on mount; resolve URL-param names → full refs after load
  useEffect(() => {
    loadDiagramData()
      .then(({ data: loadedData, sourceRoot: root }) => {
        setData(loadedData);
        setSourceRoot(root);
        setLoading(false);
        // Resolve initial URL params (captured before sync effect wiped the URL)
        if (initialSelected) setSelectedNode(resolveElementNames(loadedData, [initialSelected])[0] ?? null);
        if (initialFocus) setFocusedNode(resolveElementNames(loadedData, [initialFocus])[0] ?? null);
        setFocusTargetRefs(resolveElementNames(loadedData, initialTargetNames));
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Sync navigation state → URL using short display names, not full refs
  useEffect(() => {
    const params = new URLSearchParams();
    if (currentView !== 'root') params.set('view', currentView);
    if (selectedNode && data) {
      const name = data.elements.get(selectedNode)?.name;
      if (name) params.set('selected', name);
    }
    if (focusTargetRefs.length > 0 && data) {
      for (const ref of focusTargetRefs) {
        const name = data.elements.get(ref)?.name;
        if (name) params.append('targets', name);
      }
    } else if (focusedNode && data) {
      const name = data.elements.get(focusedNode)?.name;
      if (name) params.set('focus', name);
    }
    if (panelCollapsed) params.set('panel', 'collapsed');
    const qs = params.toString();
    window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
  }, [currentView, selectedNode, focusedNode, focusTargetRefs, data, panelCollapsed]);

  const highlightedExternalEdges = useMemo(() => {
    if (!data || !selectedNode) return new Set<string>();
    const descendants = getDescendantRefs(data, selectedNode);
    const memberRefs = new Set<string>([selectedNode, ...descendants]);
    const viewDescendants = getDescendantRefs(data, currentView);
    const viewMembers = new Set<string>([currentView, ...viewDescendants]);

    const externalKeys: string[] = [];
    for (const conn of data.connectors) {
      const sourceInside = memberRefs.has(conn.source);
      const targetInside = memberRefs.has(conn.target);
      if (sourceInside === targetInside) continue;
      const otherRef = sourceInside ? conn.target : conn.source;
      if (!viewMembers.has(otherRef)) {
        externalKeys.push(`${conn.source}-${conn.target}`);
      }
    }
    return new Set(externalKeys);
  }, [data, selectedNode, currentView]);

  const focusedTargetSet = useMemo(() => new Set(focusTargetRefs), [focusTargetRefs]);

  const handleSelect = useCallback((ref: string | null) => {
    setSelectedNode(ref);
  }, []);


  const handleShowFocus = useCallback((ref: string) => {
    setFocusTargetRefs([]);
    setFocusedNode(ref);
    setSelectedNode(ref);
    invalidateLayout(`focus:${ref}`);
    window.history.pushState({ focus: ref }, '');
  }, []);

  const handleExitFocus = useCallback(() => {
    setFocusTargetRefs([]);
    setFocusedNode(null);
  }, []);

  const handleOpenSource = useCallback((ref: string) => {
    if (!data || !sourceRoot) return;
    const elem = data.elements.get(ref);
    if (!elem?.file_path) return;
    window.open(`idea://open?file=${sourceRoot}/${elem.file_path}&line=1`, '_self');
  }, [data, sourceRoot]);

  const handleEnterGroup = useCallback(
    (ref: string) => {
      if (!data) return;

      const viewElements = getViewElements(data, currentView);
      const viewConnectors = getViewConnectors(data, currentView);
      const currentLayout = getOrComputeLayout(currentView, viewElements, viewConnectors);
      const targetNode = currentLayout.nodes.find(n => n.ref === ref);

      const action = () => {
        setNavigationStack((prev) => [...prev, ref]);
        setSelectedNode(ref);
        invalidateLayout(ref);
        window.history.pushState({ depth: navigationStack.length + 1 }, '');
      };

      if (targetNode) {
        const canvas = document.querySelector('canvas');
        if (canvas) {
          const dpr = window.devicePixelRatio || 1;
          const tState = startTransition(targetNode, canvas.width / dpr, canvas.height / dpr);
          setPendingNavigation({ transitionState: tState, action });
          return;
        }
      }

      action(); // fallback if no canvas or node
    },
    [data, currentView]
  );

  const handleGoToLevel = useCallback(
    (index: number) => {
      if (!data) return;
      const targetViewRef = navigationStack[index];
      
      const action = () => {
        setFocusedNode(null);
        setNavigationStack((prev) => prev.slice(0, index + 1));
        setSelectedNode(null);
        invalidateLayout(targetViewRef);
      };

      if (index === navigationStack.length - 2) {
        const parentElements = getViewElements(data, targetViewRef);
        const parentConnectors = getViewConnectors(data, targetViewRef);
        const parentLayout = getOrComputeLayout(targetViewRef, parentElements, parentConnectors);
        const exitingNode = parentLayout.nodes.find(n => n.ref === currentView);

        if (exitingNode) {
          const canvas = document.querySelector('canvas');
          if (canvas) {
            action();
            const dpr = window.devicePixelRatio || 1;
            const tState = startExitTransition(parentLayout, exitingNode, canvas.width / dpr, canvas.height / dpr);
            setPendingNavigation({ transitionState: tState, action: () => {} });
            return;
          }
        }
      }

      action();
    },
    [data, navigationStack, currentView]
  );

  const handleGoUp = useCallback(() => {
    if (!data) return;
    if (focusedNode || focusTargetRefs.length > 0) {
      handleExitFocus();
      return;
    }
    if (navigationStack.length <= 1) {
      setSelectedNode(null);
      return;
    }
    handleGoToLevel(navigationStack.length - 2);
  }, [data, focusedNode, focusTargetRefs, handleExitFocus, navigationStack, handleGoToLevel]);

  const handleNavigateToElement = useCallback((targetRef: string) => {
    if (!data) return;

    const targetElement = data.elements.get(targetRef);
    if (!targetElement) return;

    const targetParent = targetElement.placements[0]?.parent || 'root';

    // Target is in the current view — drill in or select
    if (targetParent === currentView) {
      setFocusedNode(null);
      setFocusTargetRefs([]);
      if (targetElement.has_view) {
        handleEnterGroup(targetRef);
      } else {
        setSelectedNode(targetRef);
      }
      return;
    }

    // Target is in a different view — navigate to its parent view, then select it
    const path: string[] = [];
    let cur = targetParent;
    while (cur !== 'root') {
      path.unshift(cur);
      const node = data.viewTree.nodes.get(cur);
      if (!node || node.parent === cur) break;
      cur = node.parent;
    }
    path.unshift('root');

    setFocusedNode(null);
    setFocusTargetRefs([]);
    setNavigationStack(path);
    setSelectedNode(targetRef);
    invalidateLayout(targetParent);
    window.history.pushState({ depth: path.length }, '');
  }, [data, currentView, handleEnterGroup]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const isTyping = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (e.target as HTMLElement)?.isContentEditable;
      if (e.key === 'Escape') {
        handleGoUp();
      } else if (!isTyping && e.key === 'f') {
        invalidateLayout(currentView);
      } else if (!isTyping && e.key === 's') {
        setPanelCollapsed((prev) => !prev);
      } else if (!isTyping && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
        e.preventDefault();
        const nodes = layoutRef.current.nodes;
        if (nodes.length === 0) return;
        const idx = nodes.findIndex(n => n.ref === selectedNode);
        const next = e.key === 'ArrowRight'
          ? nodes[(idx + 1) % nodes.length]
          : nodes[(idx - 1 + nodes.length) % nodes.length];
        handleSelect(next.ref);
      } else if (!isTyping && (e.key === 'ArrowDown' || e.key === 'Enter') && selectedNode && data) {
        e.preventDefault();
        if (data.elements.get(selectedNode)?.has_view) handleEnterGroup(selectedNode);
      } else if (!isTyping && e.key === 'ArrowUp') {
        e.preventDefault();
        handleGoUp();
      }
    };
    const handlePopState = () => {
      handleGoUp();
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('popstate', handlePopState);
    };
  }, [handleGoUp, currentView, selectedNode, data, handleSelect, handleEnterGroup]);

  const handleHover = useCallback((ref: string | null, x: number, y: number) => {
    setHoveredNode(ref);
    setMousePos({ x, y });
  }, []);

  if (loading) {
    return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>Loading...</div>;
  }

  if (error || !data) {
    return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>Error: {error}</div>;
  }

  const activeFocusRefs = focusTargetRefs.length > 0
    ? focusTargetRefs
    : focusedNode
      ? [focusedNode]
      : [];
  const focus = activeFocusRefs.length > 0
    ? computeComponentFocus(data, activeFocusRefs)
    : null;
  const viewElements = focus?.elements ?? getViewElements(data, currentView);
  const viewConnectors = focus?.connectors ?? getViewConnectors(data, currentView);
  const layoutKey = activeFocusRefs.length > 0 ? `focus:${activeFocusRefs.join('|')}` : currentView;
  const layout = getOrComputeLayout(layoutKey, viewElements, viewConnectors, 'BT');
  layoutRef.current = layout;

  // Focus views already contain every direct edge. Hierarchical views use
  // expandable stubs for connections beyond their current boundary.
  const externalStubs = activeFocusRefs.length > 0
    ? []
    : showExternalStubs
      ? computeExternalStubs(data, currentView, layout, selectedNode ?? undefined)
      : selectedNode
        ? computeExternalStubs(data, currentView, layout, selectedNode)
            .filter((stub) => stub.nodeRef === selectedNode)
        : [];

  return (
    <div className="app">
      <div className="canvas-container">
        <div className="breadcrumb">
          {navigationStack.map((item, idx) => {
            const isLast = idx === navigationStack.length - 1;
            return (
              <React.Fragment key={item}>
                {idx > 0 && <span className="breadcrumb-separator">/</span>}
                <span
                  className={`breadcrumb-item ${isLast ? 'active' : ''}`}
                  onClick={() => isLast
                    ? (activeFocusRefs.length > 0 ? handleExitFocus() : handleSelect(currentView))
                    : handleGoToLevel(idx)}
                  style={{ cursor: 'pointer', fontWeight: isLast ? 'bold' : 'normal' }}
                >
                  {item.includes('--') ? item.split('--').at(-1) : item}
                </span>
              </React.Fragment>
            );
          })}
          {activeFocusRefs.length > 0 && (
            <>
              <span className="breadcrumb-separator">/</span>
              <span className="breadcrumb-item active breadcrumb-item--focus">
                Focus: {activeFocusRefs.map((ref) => data.elements.get(ref)?.name ?? ref).join(' + ')}
              </span>
            </>
          )}
        </div>

        <img src={logoUrl} alt="TL;DR" className="app-logo" />

        <Toolbar
          showExternalStubs={showExternalStubs}
          onToggleExternalStubs={() => setShowExternalStubs(!showExternalStubs)}
          onFitToContent={() => invalidateLayout(currentView)}
        />

        <CanvasViewport
          layout={layout}
          renderState={{
            hoveredNode,
            hoveredGroupIcon,
            hoveredFocusIcon,
            hoveredSourceIcon,
            selectedNode,
            focusedNode,
            focusedNodes: focusedTargetSet,
            showExternalStubs,
            highlightedExternalEdges,
          }}
          elements={data.elements}
          externalStubs={externalStubs}
          onSelect={handleSelect}
          onEnterGroup={handleEnterGroup}
          onShowFocus={handleShowFocus}
          onHover={handleHover}
          onHoverGroupIcon={setHoveredGroupIcon}
          onHoverFocusIcon={setHoveredFocusIcon}
          onOpenSource={sourceRoot ? handleOpenSource : undefined}
          onHoverSourceIcon={setHoveredSourceIcon}
          transitionState={pendingNavigation?.transitionState}
          onTransitionComplete={() => {
            if (pendingNavigation?.action) {
              pendingNavigation.action();
            }
            setPendingNavigation(null);
          }}
        />

        {hoveredNode && (
          <Tooltip
            nodeRef={hoveredNode}
            data={data}
            x={mousePos.x}
            y={mousePos.y}
          />
        )}
      </div>

      {(selectedNode || currentView !== 'root') && (
        <SidePanel
          selectedNode={selectedNode || currentView}
          currentView={currentView}
          data={data}
          sourceRoot={sourceRoot}
          onNavigateToElement={handleNavigateToElement}
          focusedNode={focusedNode}
          onShowFocus={handleShowFocus}
          onExitFocus={handleExitFocus}
          collapsed={panelCollapsed}
          onSetCollapsed={setPanelCollapsed}
        />
      )}
    </div>
  );
};
