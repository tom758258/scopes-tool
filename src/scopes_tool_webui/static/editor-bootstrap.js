import { validateSequence, validateSequenceText } from "/static/api.js";
import { AcquisitionEditor } from "/static/acquisition-editor.js";
import { AnnotationEditor } from "/static/annotation-editor.js";
import { ChannelDisplayEditor } from "/static/channel-display-editor.js";
import { ChannelOffsetEditor } from "/static/channel-offset-editor.js";
import { ChannelScaleRangeEditor } from "/static/channel-scale-range-editor.js";
import { CursorEditor } from "/static/cursor-editor.js";
import { DemoEditor } from "/static/demo-editor.js";
import { DiagnosticsEditor } from "/static/diagnostics-editor.js";
import { ExternalTriggerEditor } from "/static/external-trigger-editor.js";
import { MeasurementEditor } from "/static/measurement-editor.js";
import { ReferenceDisplayEditor } from "/static/reference-display-editor.js";
import { ReferenceEditor } from "/static/reference-editor.js";
import { ReferenceLabelsEditor } from "/static/reference-labels-editor.js";
import { SaveExportEditor } from "/static/save-export-editor.js";
import { SearchEditor } from "/static/search-editor.js";
import { SegmentedEditor } from "/static/segmented-editor.js";
import { SequenceEditor } from "/static/sequence-editor.js";
import { SerialDecodeEditor, SerialListerEditor, SerialTriggerEditor, createSerialEditorController } from "/static/serial-editor.js";
import { TimebasePositionEditor } from "/static/timebase-position-editor.js";
import { TriggerEditor } from "/static/trigger-editor.js";
import { WgenEditor } from "/static/wgen-editor.js";
import { WorkflowEditor } from "/static/workflow-editor.js";

export function createEditorBootstrap({
  elements,
  catalog,
  executeCommand,
  isExecutionBusy,
  isCommandAvailable,
  contextKey,
  mode,
  currentModelId,
  selectedCommand,
  commandList,
  serialEditorModelInfo,
  renderPcOutputCommandNote,
  translate,
}) {
  const acquisitionEditor = new AcquisitionEditor(elements.acquisitionEditor, catalog, {
    executeCommand,
    isExecutionBusy,
    isCommandAvailable,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const referenceEditor = new ReferenceEditor(elements.referenceEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const referenceLabelsEditor = new ReferenceLabelsEditor(elements.referenceLabelsEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const referenceDisplayEditor = new ReferenceDisplayEditor(elements.referenceDisplayEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const saveExportEditor = new SaveExportEditor(elements.saveExportEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const serialWorkspaceHooks = {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    modelInfo: serialEditorModelInfo,
    renderPcOutputNote: (note) => renderPcOutputCommandNote(
      note,
      commandList()?.find((command) => command.id === "serial-lister-export"),
      elements.pcOutput,
    ),
  };
  const serialController = createSerialEditorController({
    execute: (command, parameters, options) => executeCommand(command, parameters, options),
    confirmDiscard: () => window.confirm(translate("serial.editor.discardConfirm")),
    available: () => serialWorkspaceHooks.isAvailable() && !isExecutionBusy?.(),
  });
  const serialDecodeEditor = new SerialDecodeEditor(elements.serialDecodeEditor, catalog, serialWorkspaceHooks, serialController);
  const serialTriggerEditor = new SerialTriggerEditor(elements.serialTriggerEditor, catalog, serialWorkspaceHooks, serialController);
  const serialListerEditor = new SerialListerEditor(elements.serialListerEditor, catalog, serialWorkspaceHooks, serialController);
  const triggerEditor = new TriggerEditor(elements.triggerEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const searchEditor = new SearchEditor(elements.searchEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const segmentedEditor = new SegmentedEditor(elements.segmentedEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const workflowEditor = new WorkflowEditor(elements.workflowEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const sequenceEditor = new SequenceEditor(elements.sequenceEditor, catalog, {
    executeCommand,
    validateSequence,
    validateSequenceText,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    modelId: currentModelId,
    selectedCommand,
  });
  const measurementEditor = new MeasurementEditor(elements.measurementEditor, catalog, {
    executeCommand,
    isExecutionBusy,
    isCommandAvailable,
    contextKey,
    mode,
    selectedCommand,
  });
  const channelDisplayEditor = new ChannelDisplayEditor(elements.channelDisplayEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const channelScaleRangeEditor = new ChannelScaleRangeEditor(elements.channelScaleRangeEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const externalTriggerEditor = new ExternalTriggerEditor(elements.externalTriggerEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const timebasePositionEditor = new TimebasePositionEditor(elements.timebasePositionEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
    modelId: currentModelId,
  });
  const channelOffsetEditor = new ChannelOffsetEditor(elements.channelOffsetEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const cursorEditor = new CursorEditor(elements.cursorEditor, catalog, {
    executeCommand,
    modelId: currentModelId,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const annotationEditor = new AnnotationEditor(elements.annotationEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    selectedCommand,
  });
  const wgenEditor = new WgenEditor(elements.wgenEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    mode,
    selectedCommand,
  });
  const demoEditor = new DemoEditor(elements.demoEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && isCommandAvailable(selected.id));
    },
    contextKey,
    mode,
    selectedCommand,
  });
  const diagnosticsEditor = new DiagnosticsEditor(elements.diagnosticsEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: (command) => isCommandAvailable(command),
    contextKey,
    selectedCommand,
  });

  const editorRenderers = {
    acquisition: () => acquisitionEditor,
    reference: () => referenceEditor,
    "reference-display": () => referenceDisplayEditor,
    "reference-labels": () => referenceLabelsEditor,
    "save-export": () => saveExportEditor,
    "serial-decode": () => serialDecodeEditor,
    "serial-trigger": () => serialTriggerEditor,
    "serial-lister": () => serialListerEditor,
    trigger: () => triggerEditor,
    search: () => searchEditor,
    segmented: () => segmentedEditor,
    workflow: () => workflowEditor,
    sequence: () => sequenceEditor,
    measurement: () => measurementEditor,
    cursor: () => cursorEditor,
    annotation: () => annotationEditor,
    wgen: () => wgenEditor,
    demo: () => demoEditor,
    diagnostics: () => diagnosticsEditor,
    "channel-display": () => channelDisplayEditor,
    "channel-scale-range": () => channelScaleRangeEditor,
    "external-trigger": () => externalTriggerEditor,
    "timebase-position": () => timebasePositionEditor,
    "channel-offset": () => channelOffsetEditor,
  };

  function editorKindFor(command) {
    const kind = command?.editor;
    return kind && editorRenderers[kind] ? kind : null;
  }

  return {
    acquisitionEditor,
    referenceEditor,
    referenceDisplayEditor,
    referenceLabelsEditor,
    saveExportEditor,
    serialController,
    serialDecodeEditor,
    serialTriggerEditor,
    serialListerEditor,
    triggerEditor,
    searchEditor,
    segmentedEditor,
    workflowEditor,
    sequenceEditor,
    measurementEditor,
    channelDisplayEditor,
    channelScaleRangeEditor,
    externalTriggerEditor,
    timebasePositionEditor,
    channelOffsetEditor,
    cursorEditor,
    annotationEditor,
    wgenEditor,
    demoEditor,
    diagnosticsEditor,
    editorKindFor,
  };
}
