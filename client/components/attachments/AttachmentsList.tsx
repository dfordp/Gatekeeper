'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/endpoints';
import { attachmentSchema } from '@/lib/schemas/attachment';
import { z } from 'zod';
import { Button } from '@/components/common/Button';
import { Loading } from '@/components/common/Loading';
import { EmptyState } from '@/components/common/EmptyState';
import { DeprecateModal } from './DeprecateModal';
import { helpers } from '@/lib/utils/helpers';

interface AttachmentsListProps {
  companyId: string;
  ticketId: string;
}

export const AttachmentsList: React.FC<AttachmentsListProps> = ({
  companyId,
  ticketId,
}) => {
  const [showDeprecateModal, setShowDeprecateModal] = useState(false);
  const [selectedAttachmentId, setSelectedAttachmentId] = useState<string | null>(
    null
  );

  const { data: attachments, isLoading, error } = useQuery({
    queryKey: ['attachments', companyId, ticketId],
    queryFn: async () => {
      const response = await apiClient.get(
        API_ENDPOINTS.ATTACHMENTS.LIST(companyId, ticketId)
      );

      const schema = z.object({
        success: z.boolean(),
        data: z.object({
          items: z.array(attachmentSchema),
        }),
      });

      return schema.parse(response.data).data.items;
    },
    staleTime: 1000 * 60 * 5,
  });

  const handleDownload = async (attachmentId: string, filename: string) => {
    try {
      const response = await apiClient.get(
        API_ENDPOINTS.ATTACHMENTS.DOWNLOAD(companyId, attachmentId),
        { responseType: 'blob' }
      );

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.parentElement?.removeChild(link);
    } catch (error) {
      console.error('Download failed:', error);
      alert('Failed to download file');
    }
  };

  const handleDeprecateClick = (attachmentId: string) => {
    setSelectedAttachmentId(attachmentId);
    setShowDeprecateModal(true);
  };

  if (isLoading) return <Loading />;

  if (error) {
    return (
      <EmptyState
        title="Error loading attachments"
        description="Failed to load file attachments"
      />
    );
  }

  const activeAttachments = attachments?.filter((a) => a.is_active) || [];
  const deprecatedAttachments = attachments?.filter((a) => !a.is_active) || [];

  return (
    <div className="space-y-6">
      {/* Active Attachments */}
      {activeAttachments.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Current Files
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                    Filename
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                    Size
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                    Uploaded By
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                    Date
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {activeAttachments.map((attachment) => (
                  <tr
                    key={attachment.id}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">📄</span>
                        <div>
                          <p className="font-medium text-gray-800">
                            {attachment.filename}
                          </p>
                          <p className="text-xs text-gray-500">
                            {attachment.mime_type}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {(attachment.file_size / 1024).toFixed(2)} KB
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {attachment.uploader_name}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {helpers.formatDate(attachment.created_at)}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() =>
                            handleDownload(attachment.id, attachment.filename)
                          }
                        >
                          Download
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => handleDeprecateClick(attachment.id)}
                        >
                          Deprecate
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Deprecated Attachments */}
      {deprecatedAttachments.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Deprecated Files
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                    Filename
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                    Reason
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">
                    Deprecated On
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {deprecatedAttachments.map((attachment) => (
                  <tr key={attachment.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl opacity-50">📄</span>
                        <div>
                          <p className="font-medium text-gray-600 line-through">
                            {attachment.filename}
                          </p>
                          <p className="text-xs text-gray-500">
                            {attachment.mime_type}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {attachment.deprecation_reason || 'No reason provided'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {helpers.formatDate(attachment.deprecated_at || '')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!activeAttachments.length && !deprecatedAttachments.length && (
        <EmptyState
          title="No attachments"
          description="Upload files to attach them to this ticket"
        />
      )}

      {/* Deprecate Modal */}
      {selectedAttachmentId && (
        <DeprecateModal
          isOpen={showDeprecateModal}
          companyId={companyId}
          attachmentId={selectedAttachmentId}
          onClose={() => {
            setShowDeprecateModal(false);
            setSelectedAttachmentId(null);
          }}
        />
      )}
    </div>
  );
};