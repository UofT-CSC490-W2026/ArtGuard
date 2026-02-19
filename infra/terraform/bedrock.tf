# OpenSearch Serverless Collection (Vector Database)

# Encryption policy for OpenSearch Serverless (Vector Database)
resource "aws_opensearchserverless_security_policy" "knowledge_base_encryption" {
  name = "${local.project_name}-kb-encryption"
  type = "encryption"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource = [
          "collection/${local.project_name}-knowledge-base"
        ]
      }
    ]
    AWSOwnedKey = true
  })
}

# Network policy for OpenSearch Serverless (Vector Database)
resource "aws_opensearchserverless_security_policy" "knowledge_base_network" {
  name = "${local.project_name}-kb-network"
  type = "network"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/${local.project_name}-knowledge-base"
          ]
        },
        {
          ResourceType = "dashboard"
          Resource = [
            "collection/${local.project_name}-knowledge-base"
          ]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

# Data access policy (Vector Database)
resource "aws_opensearchserverless_access_policy" "knowledge_base" {
  name = "${local.project_name}-kb-access"
  type = "data"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/${local.project_name}-knowledge-base"
          ]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems"
          ]
        },
        {
          ResourceType = "index"
          Resource = [
            "index/${local.project_name}-knowledge-base/*"
          ]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:UpdateIndex",
            "aoss:DeleteIndex"
          ]
        }
      ]
      Principal = [
        aws_iam_role.bedrock_knowledge_base.arn,
        data.aws_caller_identity.current.arn
      ]
    }
  ])
}

# OpenSearch Serverless Collection / vector database
resource "aws_opensearchserverless_collection" "knowledge_base" {
  name = "${local.project_name}-knowledge-base"
  type = "VECTORSEARCH"

  depends_on = [
    aws_opensearchserverless_security_policy.knowledge_base_encryption,
    aws_opensearchserverless_security_policy.knowledge_base_network
  ]

  tags = {
    Name    = "${local.project_name}-knowledge-base"
    Purpose = "Vector database for Bedrock Knowledge Base"
  }
}


# Create vector index inside the OpenSearch Serverless collection
resource "null_resource" "opensearch_index" {
  depends_on = [
    aws_opensearchserverless_collection.knowledge_base,
    aws_opensearchserverless_access_policy.knowledge_base
  ]

  triggers = {
    collection_endpoint = aws_opensearchserverless_collection.knowledge_base.collection_endpoint
    index_name          = var.bedrock_vector_index_name
  }

  provisioner "local-exec" {
    command = <<-EOT
      awscurl --service aoss --region ${var.aws_region} \
        -X PUT "${aws_opensearchserverless_collection.knowledge_base.collection_endpoint}/${var.bedrock_vector_index_name}" \
        -H "Content-Type: application/json" \
        -d '{
          "settings": {
            "index": { "knn": true, "knn.algo_param.ef_search": 512 }
          },
          "mappings": {
            "properties": {
              "${var.bedrock_vector_index_name}-vector": {
                "type": "knn_vector",
                "dimension": 1536,
                "method": { "engine": "faiss", "name": "hnsw" }
              },
              "AMAZON_BEDROCK_TEXT_CHUNK": { "type": "text" },
              "AMAZON_BEDROCK_METADATA": { "type": "text" }
            }
          }
        }'
    EOT
  }
}

# Bedrock Knowledge Base
resource "aws_bedrockagent_knowledge_base" "main" {
  name     = "${local.project_name}-knowledge-base"
  role_arn = aws_iam_role.bedrock_knowledge_base.arn

  knowledge_base_configuration {
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model}"
    }
    type = "VECTOR"
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"

    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.knowledge_base.arn
      vector_index_name = var.bedrock_vector_index_name

      field_mapping {
        vector_field   = "${var.bedrock_vector_index_name}-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }

  tags = {
    Name    = "${local.project_name}-knowledge-base"
    Purpose = "RAG for Bedrock"
  }

  depends_on = [
    null_resource.opensearch_index,
    aws_iam_role_policy.bedrock_kb_s3_access,
    aws_iam_role_policy.bedrock_kb_opensearch_access,
    aws_iam_role_policy.bedrock_kb_model_access
  ]
}

# Bedrock Knowledge Base Data Source (S3)
resource "aws_bedrockagent_data_source" "s3_documents" {
  name              = "${local.project_name}-s3-data-source"
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id

  data_source_configuration {
    type = "S3"

    s3_configuration {
      bucket_arn         = aws_s3_bucket.knowledge_base.arn
      inclusion_prefixes = ["documents/"]
    }
  }

  # Chunking strategy
  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = var.bedrock_chunking_strategy

      fixed_size_chunking_configuration {
        max_tokens         = var.bedrock_chunk_max_tokens
        overlap_percentage = var.bedrock_chunk_overlap_percentage
      }
    }
  }

  depends_on = [
    aws_bedrockagent_knowledge_base.main
  ]
}
