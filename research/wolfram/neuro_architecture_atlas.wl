(*
  Sovereign Neuro-Architecture research foundation.
  This file performs read-only Wolfram entity and graph analysis.
  It does not activate a runtime or establish a biological equivalence claim.
*)

ClearAll[plainValue, safeEntity, regionNames, regions, regionProperties, regionData,
  cerebellum, cerebellarNeurons, softwareGraph, softwareMetrics, result];

plainValue[value_] := Which[
  Head[value] === Entity, CommonName[value],
  Head[value] === EntityProperty, CanonicalName[value],
  AssociationQ[value], AssociationMap[plainValue, value],
  ListQ[value], plainValue /@ value,
  MissingQ[value], ToString[value, InputForm],
  True, value
];

safeEntity[name_, type_] := Quiet @ Check[
  \[FreeformPrompt][name, type],
  Missing["UnresolvedEntity", name]
];

regionNames = {
  "thalamus",
  "hypothalamus",
  "hippocampus",
  "amygdala",
  "cerebellum",
  "brainstem",
  "basal ganglia"
};

regions = AssociationMap[safeEntity[#, "AnatomicalStructure"] &, regionNames];

regionProperties = {
  "CommonName",
  "NeuronalInput",
  "NeuronalOutput",
  "Neurons"
};

regionData = AssociationMap[
  Function[entity,
    If[MissingQ[entity],
      entity,
      Quiet @ Check[
        EntityValue[entity, regionProperties, "PropertyAssociation"],
        Missing["EntityValueUnavailable", ToString[entity, InputForm]]
      ]
    ]
  ],
  regions
];

cerebellum = safeEntity["cerebellum", "AnatomicalStructure"];
cerebellarNeurons = If[MissingQ[cerebellum],
  {},
  Quiet @ Check[EntityValue[cerebellum, "Neurons"], {}]
];

softwareGraph = Graph[
  {
    "sensory-intake" -> "thalamic-routing",
    "thalamic-routing" -> "reflex-safety",
    "thalamic-routing" -> "deterministic-verification",
    "thalamic-routing" -> "cognitive-side-channel",
    "reflex-safety" -> "evidence",
    "reflex-safety" -> "motor-authorization",
    "deterministic-verification" -> "evidence",
    "deterministic-verification" -> "motor-authorization",
    "cognitive-side-channel" -> "evidence",
    "motor-authorization" -> "cerebellar-correction",
    "motor-authorization" -> "evidence",
    "cerebellar-correction" -> "evidence",
    "evidence" -> "persistence",
    "homeostasis" -> "thalamic-routing",
    "quarantine" -> "evidence"
  },
  DirectedEdges -> True,
  VertexLabels -> "Name"
];

softwareMetrics = <|
  "VertexCount" -> VertexCount[softwareGraph],
  "EdgeCount" -> EdgeCount[softwareGraph],
  "WeaklyConnectedComponents" -> ConnectedComponents[UndirectedGraph[softwareGraph]],
  "BetweennessCentrality" -> AssociationThread[
    VertexList[softwareGraph],
    BetweennessCentrality[softwareGraph]
  ],
  "PageRankCentrality" -> AssociationThread[
    VertexList[softwareGraph],
    PageRankCentrality[softwareGraph]
  ],
  "VertexDegree" -> AssociationThread[
    VertexList[softwareGraph],
    VertexDegree[softwareGraph]
  ]
|>;

result = <|
  "SchemaVersion" -> "sovereign.neuro-wolfram-atlas.v1",
  "EvidenceBoundary" -> <|
    "BiologicalNamesAreAliases" -> True,
    "ArelorianTruthPathModified" -> False,
    "RuntimeActivated" -> False
  |>,
  "RegionData" -> plainValue[regionData],
  "CerebellarNeuronCount" -> Length[cerebellarNeurons],
  "CerebellarNeurons" -> plainValue[cerebellarNeurons],
  "SoftwareGraphMetrics" -> plainValue[softwareMetrics]
|>;

result
