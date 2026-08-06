import React, { useEffect, useState, useCallback, useMemo } from 'react';
import logoUrl from './assets/logo.png';
import { loadDiagramData, getViewElements, getViewConnectors, getDescendantRefs } from './data/loader';
import { DiagramData } from './data/types';
import { computeExternalStubs } from './canvas/stubs';
import { computeComponentFocus } from './data/focus';
import { getOrComputeLayout, invalidateLayout } from './canvas/layout';
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
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [hoveredGroupIcon, setHoveredGroupIcon] = useState<string | null>(null);
  const [hoveredFocusIcon, setHoveredFocusIcon] = useState<string | null>(null);
  const [hoveredSourceIcon, setHoveredSourceIcon] = useState<string | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [showExternalStubs, setShowExternalStubs] = useState(true);
  const [focusedNode, setFocusedNode] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [pendingNavigation, setPendingNavigation] = useState<{
    transitionState: TransitionState;
    action: () => void;
  } | null>(null);

  // Load diagram data on mount; resolve URL-param names → full refs after load
  useEffect(() => {
    loadDiagramData()
      .then(({ data: loadedData, sourceRoot: root }) => {
        setData(loadedData);
        setSourceRoot(root);
        setLoading(false);
        // Resolve ?selected and ?focus from element names → full refs
        const params = new URLSearchParams(window.location.search);
        const selectedName = params.get('selected');
        const focusName = params.get('focus');
        const byName = (name: string) =>
          [...loadedData.elements.values()].find((e) => e.name === name)?.ref ?? null;
        if (selectedName) setSelectedNode(byName(selectedName));
        if (focusName) setFocusedNode(byName(focusName));
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Sync navigation state → URL (replaceState keeps history entries clean)
  // Sync navigation state → URL using short display names, not full refs
  useEffect(() => {
    const params = new URLSearchParams();
    if (currentView !== 'root') params.set('view', currentView);
    if (selectedNode && data) {
      const name = data.elements.get(selectedNode)?.name;
      if (name) params.set('selected', name);
    }
    if (focusedNode && data) {
      const name = data.elements.get(focusedNode)?.name;
      if (name) params.set('focus', name);
    }
    const qs = params.toString();
    window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
  }, [currentView, selectedNode, focusedNode, data]);

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

  const handleSelect = useCallback((ref: string | null) => {
    setSelectedNode(ref);
  }, []);


  const handleShowFocus = useCallback((ref: string) => {
    setFocusedNode(ref);
    setSelectedNode(ref);
    invalidateLayout(`focus:${ref}`);
    window.history.pushState({ focus: ref }, '');
  }, []);

  const handleExitFocus = useCallback(() => {
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
    if (focusedNode) {
      handleExitFocus();
      return;
    }
    if (navigationStack.length <= 1) {
      setSelectedNode(null);
      return;
    }
    handleGoToLevel(navigationStack.length - 2);
  }, [data, focusedNode, handleExitFocus, navigationStack, handleGoToLevel]);

  const handleNavigateToElement = useCallback((targetRef: string) => {
    if (!data) return;

    const targetElement = data.elements.get(targetRef);
    if (!targetElement) return;

    const targetParent = targetElement.placements[0]?.parent || 'root';

    // Target is in the current view — drill in or select
    if (targetParent === currentView) {
      setFocusedNode(null);
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
    setNavigationStack(path);
    setSelectedNode(targetRef);
    invalidateLayout(targetParent);
    window.history.pushState({ depth: path.length }, '');
  }, [data, currentView, handleEnterGroup]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
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
  }, [handleGoUp]);

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

  const focus = focusedNode
    ? computeComponentFocus(data, focusedNode)
    : null;
  const viewElements = focus?.elements ?? getViewElements(data, currentView);
  const viewConnectors = focus?.connectors ?? getViewConnectors(data, currentView);
  const layoutKey = focusedNode ? `focus:${focusedNode}` : currentView;
  const layout = getOrComputeLayout(layoutKey, viewElements, viewConnectors, 'BT');

  // Focus views already contain every direct edge. Hierarchical views use
  // expandable stubs for connections beyond their current boundary.
  const externalStubs = focusedNode
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
                    ? (focusedNode ? handleExitFocus() : handleSelect(currentView))
                    : handleGoToLevel(idx)}
                  style={{ cursor: 'pointer', fontWeight: isLast ? 'bold' : 'normal' }}
                >
                  {item.includes('--') ? item.split('--').at(-1) : item}
                </span>
              </React.Fragment>
            );
          })}
          {focusedNode && (
            <>
              <span className="breadcrumb-separator">/</span>
              <span className="breadcrumb-item active breadcrumb-item--focus">
                Focus: {data.elements.get(focusedNode)?.name ?? focusedNode}
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
