'use client';

import React, { useState } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { useTicket } from '@/lib/hooks/useTicket';
import { useAddComment } from '@/lib/hooks/useAddComment';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Loading } from '@/components/common/Loading';
import { AssignModal } from './AssignModal';
import { LevelModal } from './LevelModal';
import { StatusModal } from './StatusModal';
import { FileUpload } from '@/components/attachments/FileUpload';
import { AttachmentsList } from '@/components/attachments/AttachmentsList';
import { helpers } from '@/lib/utils/helpers';

interface TicketDetailProps {
  companyId: string;
  ticketId: string;
}

export const TicketDetail: React.FC<TicketDetailProps> = ({
  companyId,
  ticketId,
}) => {
  const { user } = useAuth();
  const { data: ticket, isLoading } = useTicket({
    companyId,
    ticketId,
  });

  const { mutate: addComment, isPending: isCommenting } = useAddComment(
    companyId,
    ticketId
  );

  const [comment, setComment] = useState('');
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [showLevelModal, setShowLevelModal] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [showFileUpload, setShowFileUpload] = useState(false);

  const handleAddComment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!comment.trim()) return;

    addComment(
      { text: comment },
      { onSuccess: () => setComment('') }
    );
  };

  if (isLoading) return <Loading />;

  if (!ticket) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Ticket not found</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-sm text-gray-500">{ticket.ticket_number}</p>
            <h1 className="text-2xl font-bold text-gray-800 mt-1">
              {ticket.title}
            </h1>
          </div>
          <div className="flex gap-2">
            <Badge variant="status" value={ticket.status} />
            <Badge variant="level" value={ticket.level} />
            <Badge variant="category" value={ticket.category} />
          </div>
        </div>

        <p className="text-gray-600 mb-6">{ticket.description}</p>

        {/* Metadata */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 pb-6 border-b border-gray-200">
          <div>
            <p className="text-xs text-gray-500">Created</p>
            <p className="text-sm font-medium text-gray-800">
              {helpers.formatDate(ticket.created_at)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Last Updated</p>
            <p className="text-sm font-medium text-gray-800">
              {helpers.formatDate(ticket.updated_at)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Assigned To</p>
            <p className="text-sm font-medium text-gray-800">
              {ticket.assigned_to ? 'Engineer' : 'Unassigned'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Priority</p>
            <p className="text-sm font-medium text-gray-800">
              {ticket.level}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowAssignModal(true)}
          >
            Assign
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowLevelModal(true)}
          >
            Change Level
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowStatusModal(true)}
          >
            Change Status
          </Button>
        </div>
      </div>

      {/* Attachments Section */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">Attachments</h2>
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowFileUpload(!showFileUpload)}
          >
            {showFileUpload ? 'Hide Upload' : 'Upload File'}
          </Button>
        </div>

        {showFileUpload && (
          <div className="mb-6 pb-6 border-b border-gray-200">
            <FileUpload
              companyId={companyId}
              ticketId={ticketId}
              onSuccess={() => setShowFileUpload(false)}
            />
          </div>
        )}

        <AttachmentsList companyId={companyId} ticketId={ticketId} />
      </div>

      {/* Comments Section */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Comments</h2>

        <form onSubmit={handleAddComment} className="mb-6 pb-6 border-b border-gray-200">
          <div className="flex gap-3">
            <Input
              type="text"
              placeholder="Add a comment..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="flex-1"
            />
            <Button
              type="submit"
              variant="primary"
              isLoading={isCommenting}
              disabled={!comment.trim()}
            >
              Post
            </Button>
          </div>
        </form>

        <div className="space-y-4">
          <div className="text-center py-8 text-gray-500">
            <p>No comments yet. Be the first to comment!</p>
          </div>
        </div>
      </div>

      {/* Modals */}
      <AssignModal
        isOpen={showAssignModal}
        companyId={companyId}
        ticketId={ticketId}
        onClose={() => setShowAssignModal(false)}
      />

      <LevelModal
        isOpen={showLevelModal}
        companyId={companyId}
        ticketId={ticketId}
        currentLevel={ticket.level}
        onClose={() => setShowLevelModal(false)}
      />

      <StatusModal
        isOpen={showStatusModal}
        companyId={companyId}
        ticketId={ticketId}
        currentStatus={ticket.status}
        onClose={() => setShowStatusModal(false)}
      />
    </div>
  );
};