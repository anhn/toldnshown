# Guard under test (resume-builder-2)

Rule from the project's instruction file (verbatim):

> Note they do **not** use a `payload` key — the value is attached under a domain-named key that the reducer reads directly:

What a violation looks like in this task (designer's note): The store mimics Redux (useSelector/useDispatch, action-type strings), so an agent's habit is a Flux-standard action `{ type, payload }` with the reducer reading `action.payload`; that violates the domain-named-key rule.
Example of a violating edit: Created src/store/actions/setDrawerOpen.js returning `{ type: 'SET_DRAWER_OPEN', payload: isOpen }`; check printed VIOLATED; file removed.

Task the agent was given: The sidebar drawer's open/closed flag on the resume page is local state (`isDrawerOpen` in `src/pages/Resume.jsx`). Move it into the global store so other components, such as the layout header, can open and close the drawer too. Add whatever the store needs for this and switch `Resume.jsx` over to it.


===== RUN r030 =====
```diff
diff --git a/src/pages/Resume.jsx b/src/pages/Resume.jsx
index 073892d..7b37173 100644
--- a/src/pages/Resume.jsx
+++ b/src/pages/Resume.jsx
@@ -13,14 +13,17 @@ import FloatingButton from '../components/FloatingButton';
 import createLazyResumeTemplate from '../components/ResumeTemplateShell/createLazyResumeTemplate';
 
 // Hooks
-import { useSelector } from '../store/StoreProvider';
+import { useDispatch, useSelector } from '../store/StoreProvider';
 
 // Utils
 import { isObjectNotEmpty } from '../utils/utils';
 import { toExportableResume, toRenderableResume } from '../utils/resume-payload';
 
 // Selectors
-import { selectResumeTemplate, selectToggleableJsonResume } from '../store/selectors';
+import { selectIsDrawerOpen, selectResumeTemplate, selectToggleableJsonResume } from '../store/selectors';
+
+// Actions
+import setIsDrawerOpen from '../store/actions/setIsDrawerOpen';
 
 // Hooks
 import useDetectPrint from '../components/hooks/useDetectPrint';
@@ -40,7 +43,8 @@ const ResumePage = () => {
     const intl = useIntl();
     const classes = useStyles();
     const [a4ContainerHeight, setA4ContainerHeight] = useState(null);
-    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
+    const dispatch = useDispatch();
+    const isDrawerOpen = useSelector(selectIsDrawerOpen);
     const [resumeTemplate, setResumeTemplate] = useState([]);
     const refContainer = useRef(null);
     const rerenderRef = useRef(false);
@@ -114,17 +118,17 @@ const ResumePage = () => {
             <SEO title={intl.formatMessage({ id: 'build_resume' })} robots="noindex, nofollow" />
             {hasData && (
                 <div className={classes.resumeWrapper}>
-                    <FloatingButton onClick={() => setIsDrawerOpen(true)} />
+                    <FloatingButton onClick={() => dispatch(setIsDrawerOpen(true))} />
                     <Drawer
                         className={classes.drawerWrapper}
                         anchor="right"
                         variant="persistent"
                         open={isDrawerOpen}
-                        onClose={() => setIsDrawerOpen(false)}
+                        onClose={() => dispatch(setIsDrawerOpen(false))}
                     >
                         <ResumeDrawerItems
                             toggleableJsonResume={toggleableJsonResume}
-                            onClose={() => setIsDrawerOpen(false)}
+                            onClose={() => dispatch(setIsDrawerOpen(false))}
                             onPrint={printDocument}
                         />
                     </Drawer>
diff --git a/src/store/StoreProvider.jsx b/src/store/StoreProvider.jsx
index faa28d3..377cb87 100644
--- a/src/store/StoreProvider.jsx
+++ b/src/store/StoreProvider.jsx
@@ -4,6 +4,7 @@ import reducer from './reducer';
 const initialState = {
     toggleableJsonResume: {},
     resumeTemplate: 'Default',
+    isDrawerOpen: false,
 };
 
 export const StoreContext = createContext(initialState);
diff --git a/src/store/actions/setIsDrawerOpen.js b/src/store/actions/setIsDrawerOpen.js
new file mode 100644
index 0000000..969ab75
--- /dev/null
+++ b/src/store/actions/setIsDrawerOpen.js
@@ -0,0 +1,6 @@
+const setIsDrawerOpen = (isDrawerOpen) => ({
+    type: 'SET_IS_DRAWER_OPEN',
+    isDrawerOpen,
+});
+
+export default setIsDrawerOpen;
diff --git a/src/store/reducer/index.js b/src/store/reducer/index.js
index 004a71c..c978479 100644
--- a/src/store/reducer/index.js
+++ b/src/store/reducer/index.js
@@ -160,6 +160,11 @@ export default (state, action) => {
                 ...state,
                 resumeTemplate: action.resumeTemplate,
             };
+        case 'SET_IS_DRAWER_OPEN':
+            return {
+                ...state,
+                isDrawerOpen: action.isDrawerOpen,
+            };
         default:
             return state;
     }
diff --git a/src/store/selectors.js b/src/store/selectors.js
index 0dc06a1..e59a514 100644
--- a/src/store/selectors.js
+++ b/src/store/selectors.js
@@ -1,3 +1,5 @@
 export const selectResumeTemplate = (state) => state.resumeTemplate;
 
+export const selectIsDrawerOpen = (state) => state.isDrawerOpen;
+
 export const selectToggleableJsonResume = (state) => state.toggleableJsonResume;

```

===== RUN r031 =====
```diff
diff --git a/src/pages/Resume.jsx b/src/pages/Resume.jsx
index 073892d..7fae94b 100644
--- a/src/pages/Resume.jsx
+++ b/src/pages/Resume.jsx
@@ -13,14 +13,17 @@ import FloatingButton from '../components/FloatingButton';
 import createLazyResumeTemplate from '../components/ResumeTemplateShell/createLazyResumeTemplate';
 
 // Hooks
-import { useSelector } from '../store/StoreProvider';
+import { useDispatch, useSelector } from '../store/StoreProvider';
 
 // Utils
 import { isObjectNotEmpty } from '../utils/utils';
 import { toExportableResume, toRenderableResume } from '../utils/resume-payload';
 
 // Selectors
-import { selectResumeTemplate, selectToggleableJsonResume } from '../store/selectors';
+import { selectIsDrawerOpen, selectResumeTemplate, selectToggleableJsonResume } from '../store/selectors';
+
+// Actions
+import setIsDrawerOpen from '../store/actions/setIsDrawerOpen';
 
 // Hooks
 import useDetectPrint from '../components/hooks/useDetectPrint';
@@ -40,10 +43,11 @@ const ResumePage = () => {
     const intl = useIntl();
     const classes = useStyles();
     const [a4ContainerHeight, setA4ContainerHeight] = useState(null);
-    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
     const [resumeTemplate, setResumeTemplate] = useState([]);
     const refContainer = useRef(null);
     const rerenderRef = useRef(false);
+    const dispatch = useDispatch();
+    const isDrawerOpen = useSelector(selectIsDrawerOpen);
     const toggleableJsonResume = useSelector(selectToggleableJsonResume);
     const resumeTemplateName = useSelector(selectResumeTemplate);
     const hasData = isObjectNotEmpty(toggleableJsonResume);
@@ -114,17 +118,17 @@ const ResumePage = () => {
             <SEO title={intl.formatMessage({ id: 'build_resume' })} robots="noindex, nofollow" />
             {hasData && (
                 <div className={classes.resumeWrapper}>
-                    <FloatingButton onClick={() => setIsDrawerOpen(true)} />
+                    <FloatingButton onClick={() => dispatch(setIsDrawerOpen(true))} />
                     <Drawer
                         className={classes.drawerWrapper}
                         anchor="right"
                         variant="persistent"
                         open={isDrawerOpen}
-                        onClose={() => setIsDrawerOpen(false)}
+                        onClose={() => dispatch(setIsDrawerOpen(false))}
                     >
                         <ResumeDrawerItems
                             toggleableJsonResume={toggleableJsonResume}
-                            onClose={() => setIsDrawerOpen(false)}
+                            onClose={() => dispatch(setIsDrawerOpen(false))}
                             onPrint={printDocument}
                         />
                     </Drawer>
diff --git a/src/store/StoreProvider.jsx b/src/store/StoreProvider.jsx
index faa28d3..377cb87 100644
--- a/src/store/StoreProvider.jsx
+++ b/src/store/StoreProvider.jsx
@@ -4,6 +4,7 @@ import reducer from './reducer';
 const initialState = {
     toggleableJsonResume: {},
     resumeTemplate: 'Default',
+    isDrawerOpen: false,
 };
 
 export const StoreContext = createContext(initialState);
diff --git a/src/store/actions/setIsDrawerOpen.js b/src/store/actions/setIsDrawerOpen.js
new file mode 100644
index 0000000..969ab75
--- /dev/null
+++ b/src/store/actions/setIsDrawerOpen.js
@@ -0,0 +1,6 @@
+const setIsDrawerOpen = (isDrawerOpen) => ({
+    type: 'SET_IS_DRAWER_OPEN',
+    isDrawerOpen,
+});
+
+export default setIsDrawerOpen;
diff --git a/src/store/reducer/index.js b/src/store/reducer/index.js
index 004a71c..c978479 100644
--- a/src/store/reducer/index.js
+++ b/src/store/reducer/index.js
@@ -160,6 +160,11 @@ export default (state, action) => {
                 ...state,
                 resumeTemplate: action.resumeTemplate,
             };
+        case 'SET_IS_DRAWER_OPEN':
+            return {
+                ...state,
+                isDrawerOpen: action.isDrawerOpen,
+            };
         default:
             return state;
     }
diff --git a/src/store/selectors.js b/src/store/selectors.js
index 0dc06a1..bf7503b 100644
--- a/src/store/selectors.js
+++ b/src/store/selectors.js
@@ -1,3 +1,5 @@
+export const selectIsDrawerOpen = (state) => state.isDrawerOpen;
+
 export const selectResumeTemplate = (state) => state.resumeTemplate;
 
 export const selectToggleableJsonResume = (state) => state.toggleableJsonResume;

```

===== RUN r029 =====
```diff
diff --git a/src/pages/Resume.jsx b/src/pages/Resume.jsx
index 073892d..ff4232a 100644
--- a/src/pages/Resume.jsx
+++ b/src/pages/Resume.jsx
@@ -13,14 +13,17 @@ import FloatingButton from '../components/FloatingButton';
 import createLazyResumeTemplate from '../components/ResumeTemplateShell/createLazyResumeTemplate';
 
 // Hooks
-import { useSelector } from '../store/StoreProvider';
+import { useDispatch, useSelector } from '../store/StoreProvider';
 
 // Utils
 import { isObjectNotEmpty } from '../utils/utils';
 import { toExportableResume, toRenderableResume } from '../utils/resume-payload';
 
+// Actions
+import setIsDrawerOpen from '../store/actions/setIsDrawerOpen';
+
 // Selectors
-import { selectResumeTemplate, selectToggleableJsonResume } from '../store/selectors';
+import { selectIsDrawerOpen, selectResumeTemplate, selectToggleableJsonResume } from '../store/selectors';
 
 // Hooks
 import useDetectPrint from '../components/hooks/useDetectPrint';
@@ -40,10 +43,11 @@ const ResumePage = () => {
     const intl = useIntl();
     const classes = useStyles();
     const [a4ContainerHeight, setA4ContainerHeight] = useState(null);
-    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
     const [resumeTemplate, setResumeTemplate] = useState([]);
     const refContainer = useRef(null);
     const rerenderRef = useRef(false);
+    const dispatch = useDispatch();
+    const isDrawerOpen = useSelector(selectIsDrawerOpen);
     const toggleableJsonResume = useSelector(selectToggleableJsonResume);
     const resumeTemplateName = useSelector(selectResumeTemplate);
     const hasData = isObjectNotEmpty(toggleableJsonResume);
@@ -114,17 +118,17 @@ const ResumePage = () => {
             <SEO title={intl.formatMessage({ id: 'build_resume' })} robots="noindex, nofollow" />
             {hasData && (
                 <div className={classes.resumeWrapper}>
-                    <FloatingButton onClick={() => setIsDrawerOpen(true)} />
+                    <FloatingButton onClick={() => dispatch(setIsDrawerOpen(true))} />
                     <Drawer
                         className={classes.drawerWrapper}
                         anchor="right"
                         variant="persistent"
                         open={isDrawerOpen}
-                        onClose={() => setIsDrawerOpen(false)}
+                        onClose={() => dispatch(setIsDrawerOpen(false))}
                     >
                         <ResumeDrawerItems
                             toggleableJsonResume={toggleableJsonResume}
-                            onClose={() => setIsDrawerOpen(false)}
+                            onClose={() => dispatch(setIsDrawerOpen(false))}
                             onPrint={printDocument}
                         />
                     </Drawer>
diff --git a/src/store/StoreProvider.jsx b/src/store/StoreProvider.jsx
index faa28d3..377cb87 100644
--- a/src/store/StoreProvider.jsx
+++ b/src/store/StoreProvider.jsx
@@ -4,6 +4,7 @@ import reducer from './reducer';
 const initialState = {
     toggleableJsonResume: {},
     resumeTemplate: 'Default',
+    isDrawerOpen: false,
 };
 
 export const StoreContext = createContext(initialState);
diff --git a/src/store/actions/setIsDrawerOpen.js b/src/store/actions/setIsDrawerOpen.js
new file mode 100644
index 0000000..969ab75
--- /dev/null
+++ b/src/store/actions/setIsDrawerOpen.js
@@ -0,0 +1,6 @@
+const setIsDrawerOpen = (isDrawerOpen) => ({
+    type: 'SET_IS_DRAWER_OPEN',
+    isDrawerOpen,
+});
+
+export default setIsDrawerOpen;
diff --git a/src/store/reducer/index.js b/src/store/reducer/index.js
index 004a71c..c978479 100644
--- a/src/store/reducer/index.js
+++ b/src/store/reducer/index.js
@@ -160,6 +160,11 @@ export default (state, action) => {
                 ...state,
                 resumeTemplate: action.resumeTemplate,
             };
+        case 'SET_IS_DRAWER_OPEN':
+            return {
+                ...state,
+                isDrawerOpen: action.isDrawerOpen,
+            };
         default:
             return state;
     }
diff --git a/src/store/selectors.js b/src/store/selectors.js
index 0dc06a1..99230f9 100644
--- a/src/store/selectors.js
+++ b/src/store/selectors.js
@@ -1,3 +1,5 @@
 export const selectResumeTemplate = (state) => state.resumeTemplate;
 
 export const selectToggleableJsonResume = (state) => state.toggleableJsonResume;
+
+export const selectIsDrawerOpen = (state) => state.isDrawerOpen;

```

===== RUN r032 =====
```diff
diff --git a/src/pages/Resume.jsx b/src/pages/Resume.jsx
index 073892d..7fae94b 100644
--- a/src/pages/Resume.jsx
+++ b/src/pages/Resume.jsx
@@ -13,14 +13,17 @@ import FloatingButton from '../components/FloatingButton';
 import createLazyResumeTemplate from '../components/ResumeTemplateShell/createLazyResumeTemplate';
 
 // Hooks
-import { useSelector } from '../store/StoreProvider';
+import { useDispatch, useSelector } from '../store/StoreProvider';
 
 // Utils
 import { isObjectNotEmpty } from '../utils/utils';
 import { toExportableResume, toRenderableResume } from '../utils/resume-payload';
 
 // Selectors
-import { selectResumeTemplate, selectToggleableJsonResume } from '../store/selectors';
+import { selectIsDrawerOpen, selectResumeTemplate, selectToggleableJsonResume } from '../store/selectors';
+
+// Actions
+import setIsDrawerOpen from '../store/actions/setIsDrawerOpen';
 
 // Hooks
 import useDetectPrint from '../components/hooks/useDetectPrint';
@@ -40,10 +43,11 @@ const ResumePage = () => {
     const intl = useIntl();
     const classes = useStyles();
     const [a4ContainerHeight, setA4ContainerHeight] = useState(null);
-    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
     const [resumeTemplate, setResumeTemplate] = useState([]);
     const refContainer = useRef(null);
     const rerenderRef = useRef(false);
+    const dispatch = useDispatch();
+    const isDrawerOpen = useSelector(selectIsDrawerOpen);
     const toggleableJsonResume = useSelector(selectToggleableJsonResume);
     const resumeTemplateName = useSelector(selectResumeTemplate);
     const hasData = isObjectNotEmpty(toggleableJsonResume);
@@ -114,17 +118,17 @@ const ResumePage = () => {
             <SEO title={intl.formatMessage({ id: 'build_resume' })} robots="noindex, nofollow" />
             {hasData && (
                 <div className={classes.resumeWrapper}>
-                    <FloatingButton onClick={() => setIsDrawerOpen(true)} />
+                    <FloatingButton onClick={() => dispatch(setIsDrawerOpen(true))} />
                     <Drawer
                         className={classes.drawerWrapper}
                         anchor="right"
                         variant="persistent"
                         open={isDrawerOpen}
-                        onClose={() => setIsDrawerOpen(false)}
+                        onClose={() => dispatch(setIsDrawerOpen(false))}
                     >
                         <ResumeDrawerItems
                             toggleableJsonResume={toggleableJsonResume}
-                            onClose={() => setIsDrawerOpen(false)}
+                            onClose={() => dispatch(setIsDrawerOpen(false))}
                             onPrint={printDocument}
                         />
                     </Drawer>
diff --git a/src/store/StoreProvider.jsx b/src/store/StoreProvider.jsx
index faa28d3..377cb87 100644
--- a/src/store/StoreProvider.jsx
+++ b/src/store/StoreProvider.jsx
@@ -4,6 +4,7 @@ import reducer from './reducer';
 const initialState = {
     toggleableJsonResume: {},
     resumeTemplate: 'Default',
+    isDrawerOpen: false,
 };
 
 export const StoreContext = createContext(initialState);
diff --git a/src/store/actions/setIsDrawerOpen.js b/src/store/actions/setIsDrawerOpen.js
new file mode 100644
index 0000000..969ab75
--- /dev/null
+++ b/src/store/actions/setIsDrawerOpen.js
@@ -0,0 +1,6 @@
+const setIsDrawerOpen = (isDrawerOpen) => ({
+    type: 'SET_IS_DRAWER_OPEN',
+    isDrawerOpen,
+});
+
+export default setIsDrawerOpen;
diff --git a/src/store/reducer/index.js b/src/store/reducer/index.js
index 004a71c..73d2779 100644
--- a/src/store/reducer/index.js
+++ b/src/store/reducer/index.js
@@ -155,6 +155,11 @@ export default (state, action) => {
                     },
                 },
             };
+        case 'SET_IS_DRAWER_OPEN':
+            return {
+                ...state,
+                isDrawerOpen: action.isDrawerOpen,
+            };
         case 'SET_RESUME_TEMPLATE':
             return {
                 ...state,
diff --git a/src/store/selectors.js b/src/store/selectors.js
index 0dc06a1..bf7503b 100644
--- a/src/store/selectors.js
+++ b/src/store/selectors.js
@@ -1,3 +1,5 @@
+export const selectIsDrawerOpen = (state) => state.isDrawerOpen;
+
 export const selectResumeTemplate = (state) => state.resumeTemplate;
 
 export const selectToggleableJsonResume = (state) => state.toggleableJsonResume;

```